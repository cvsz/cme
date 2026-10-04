from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from cme_api.models import AuthSession, User
from cme_api.sessions import IssuedSession, issue_session, session_is_active, token_digest


class InvalidSessionError(ValueError):
    pass


class SessionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        lifetime: timedelta = timedelta(hours=12),
    ) -> tuple[AuthSession, IssuedSession]:
        issued = issue_session(lifetime=lifetime)
        record = AuthSession(
            tenant_id=tenant_id,
            user_id=user_id,
            token_digest=issued.token_digest,
            csrf_token=issued.csrf_token,
            expires_at=issued.expires_at,
        )
        self.db.add(record)
        self.db.flush()
        return record, issued

    def _authenticate(
        self,
        *,
        token: str,
        tenant_id: UUID | None = None,
        for_update: bool = False,
    ) -> AuthSession:
        digest = token_digest(token)
        statement = (
            select(AuthSession)
            .join(
                User,
                (User.tenant_id == AuthSession.tenant_id) & (User.id == AuthSession.user_id),
            )
            .where(
                AuthSession.token_digest == digest,
                User.is_active.is_(True),
            )
        )
        if tenant_id is not None:
            statement = statement.where(AuthSession.tenant_id == tenant_id)
        if for_update:
            statement = statement.with_for_update(of=AuthSession)

        record = self.db.scalar(statement)
        if record is None or not session_is_active(
            expires_at=record.expires_at, revoked_at=record.revoked_at
        ):
            raise InvalidSessionError("invalid or expired session")
        return record

    def authenticate(self, *, token: str, tenant_id: UUID | None = None) -> AuthSession:
        return self._authenticate(token=token, tenant_id=tenant_id)

    def revoke(self, *, token: str, tenant_id: UUID | None = None) -> AuthSession:
        record = self._authenticate(token=token, tenant_id=tenant_id, for_update=True)
        record.revoked_at = datetime.now(UTC)
        self.db.flush()
        return record

    def rotate(
        self, *, token: str, tenant_id: UUID | None = None
    ) -> tuple[AuthSession, IssuedSession]:
        previous = self._authenticate(token=token, tenant_id=tenant_id, for_update=True)
        now = datetime.now(UTC)
        previous.revoked_at = now
        record, issued = self.create(
            tenant_id=previous.tenant_id,
            user_id=previous.user_id,
            lifetime=max(previous.expires_at - now, timedelta(minutes=1)),
        )
        self.db.flush()
        return record, issued
