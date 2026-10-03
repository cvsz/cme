from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from cme_api.models import AuthSession
from cme_api.sessions import IssuedSession, issue_session, session_is_active, token_digest


class InvalidSessionError(ValueError):
    pass


class SessionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, *, tenant_id: UUID, user_id: UUID, lifetime: timedelta = timedelta(hours=12)) -> tuple[AuthSession, IssuedSession]:
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

    def authenticate(self, *, token: str, tenant_id: UUID | None = None) -> AuthSession:
        digest = token_digest(token)
        statement = select(AuthSession).where(AuthSession.token_digest == digest)
        if tenant_id is not None:
            statement = statement.where(AuthSession.tenant_id == tenant_id)
        record = self.db.scalar(statement)
        if record is None or not session_is_active(
            expires_at=record.expires_at, revoked_at=record.revoked_at
        ):
            raise InvalidSessionError("invalid or expired session")
        return record

    def revoke(self, *, token: str, tenant_id: UUID | None = None) -> AuthSession:
        record = self.authenticate(token=token, tenant_id=tenant_id)
        record.revoked_at = datetime.now(UTC)
        self.db.flush()
        return record

    def rotate(self, *, token: str, tenant_id: UUID | None = None) -> tuple[AuthSession, IssuedSession]:
        previous = self.authenticate(token=token, tenant_id=tenant_id)
        previous.revoked_at = datetime.now(UTC)
        record, issued = self.create(
            tenant_id=previous.tenant_id,
            user_id=previous.user_id,
            lifetime=max(previous.expires_at - datetime.now(UTC), timedelta(minutes=1)),
        )
        self.db.flush()
        return record, issued
