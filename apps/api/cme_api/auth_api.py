from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from cme_api.audit import record_audit_event
from cme_api.db import get_session
from cme_api.models import AuthSession, User
from cme_api.security import hash_password, verify_password
from cme_api.session_service import InvalidSessionError, SessionService

SESSION_COOKIE = "__Host-cme_session"
CSRF_COOKIE = "__Host-cme_csrf"
_LOGIN_WINDOW_SECONDS = 60.0
_LOGIN_MAX_ATTEMPTS = 10
_DUMMY_HASH = hash_password("cme-dummy-password-not-a-user")
_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_login_attempts_lock = Lock()
router = APIRouter(prefix="/auth", tags=["authentication"])
Db = Annotated[Session, Depends(get_session)]


class LoginRequest(BaseModel):
    email: str
    password: str


class SessionIdentity(BaseModel):
    user_id: str
    tenant_id: str
    email: str


def _set_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _set_auth_cookies(response: Response, *, token: str, csrf_token: str) -> None:
    _set_no_store(response)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=True, samesite="lax", path="/")
    response.set_cookie(
        CSRF_COOKIE, csrf_token, httponly=False, secure=True, samesite="lax", path="/"
    )


def _clear_auth_cookies(response: Response) -> None:
    _set_no_store(response)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=True, httponly=False, samesite="lax")


def _require_csrf(csrf_cookie: str | None, csrf_header: str | None) -> None:
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid csrf token")


def _rate_limit_login(request: Request, email: str) -> None:
    host = request.client.host if request.client else "unknown"
    key = f"{host}:{email.casefold()}"
    now = time.monotonic()
    with _login_attempts_lock:
        attempts = _login_attempts[key]
        while attempts and now - attempts[0] >= _LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many attempts"
            )
        attempts.append(now)


def _session(db: Session, token: str | None) -> AuthSession:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    try:
        return SessionService(db).authenticate(token=token)
    except InvalidSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized"
        ) from exc


@router.post("/login", response_model=SessionIdentity)
def login(payload: LoginRequest, request: Request, response: Response, db: Db) -> SessionIdentity:
    _rate_limit_login(request, payload.email)
    users = list(
        db.scalars(
            select(User).where(User.email == payload.email, User.is_active.is_(True)).limit(2)
        )
    )
    if not users:
        verify_password(payload.password, _DUMMY_HASH)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    matches = [user for user in users if verify_password(payload.password, user.password_hash)]
    if len(matches) != 1:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    user = matches[0]
    _, issued = SessionService(db).create(tenant_id=user.tenant_id, user_id=user.id)
    record_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action="auth.login",
        entity_type="auth_session",
    )
    db.commit()
    _set_auth_cookies(response, token=issued.token, csrf_token=issued.csrf_token)
    return SessionIdentity(user_id=str(user.id), tenant_id=str(user.tenant_id), email=user.email)


@router.get("/me", response_model=SessionIdentity)
def me(
    response: Response,
    db: Db,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> SessionIdentity:
    _set_no_store(response)
    record = _session(db, session_token)
    user = db.scalar(
        select(User).where(User.id == record.user_id, User.tenant_id == record.tenant_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    return SessionIdentity(user_id=str(user.id), tenant_id=str(user.tenant_id), email=user.email)


@router.post("/rotate", status_code=status.HTTP_204_NO_CONTENT)
def rotate(
    response: Response,
    db: Db,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    _require_csrf(csrf_cookie, csrf_header)
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    try:
        record, issued = SessionService(db).rotate(token=session_token)
        record_audit_event(
            db,
            tenant_id=record.tenant_id,
            actor_user_id=record.user_id,
            action="auth.session.rotate",
            entity_type="auth_session",
        )
    except InvalidSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized"
        ) from exc
    db.commit()
    _set_auth_cookies(response, token=issued.token, csrf_token=issued.csrf_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Db,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    _require_csrf(csrf_cookie, csrf_header)
    if session_token:
        try:
            record = SessionService(db).revoke(token=session_token)
            record_audit_event(
                db,
                tenant_id=record.tenant_id,
                actor_user_id=record.user_id,
                action="auth.logout",
                entity_type="auth_session",
            )
            db.commit()
        except InvalidSessionError:
            db.rollback()
    _clear_auth_cookies(response)
