from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID


@dataclass(frozen=True)
class IssuedSession:
    token: str
    token_digest: str
    csrf_token: str
    expires_at: datetime


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session(*, lifetime: timedelta = timedelta(hours=12)) -> IssuedSession:
    token = secrets.token_urlsafe(48)
    return IssuedSession(
        token=token,
        token_digest=token_digest(token),
        csrf_token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + lifetime,
    )


def session_is_active(\n    *, expires_at: datetime, revoked_at: datetime | None, now: datetime | None = None\n) -> bool:
    current = now or datetime.now(UTC)
    return revoked_at is None and expires_at > current


def csrf_matches(*, cookie_token: str | None, header_token: str | None) -> bool:
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)


@dataclass(frozen=True)
class SessionIdentity:
    session_id: UUID
    user_id: UUID
    tenant_id: UUID
