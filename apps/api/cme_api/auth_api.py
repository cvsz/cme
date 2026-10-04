from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from cme_api.db import get_session
from cme_api.models import AuthSession, User
from cme_api.security import verify_password
from cme_api.session_service import InvalidSessionError, SessionService

SESSION_COOKIE = "cme_session"
CSRF_COOKIE = "cme_csrf"
router = APIRouter(prefix="/auth", tags=["authentication"])
Db = Annotated[Session, Depends(get_session)]


class LoginRequest(BaseModel):
    email: str
    password: str


class SessionIdentity(BaseModel):
    user_id: str
    tenant_id: str
    email: str


def _set_auth_cookies(response: Response, *, token: str, csrf_token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=True, samesite="lax", path="/")
    response.set_cookie(
        CSRF_COOKIE, csrf_token, httponly=False, secure=True, samesite="lax", path="/"
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=True, httponly=False, samesite="lax")


def _require_csrf(csrf_cookie: str | None, csrf_header: str | None) -> None:
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid csrf token")


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
def login(payload: LoginRequest, response: Response, db: Db) -> SessionIdentity:
    users = list(
        db.scalars(select(User).where(User.email == payload.email, User.is_active.is_(True)))
    )
    matches = [user for user in users if verify_password(payload.password, user.password_hash)]
    if len(matches) != 1:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    user = matches[0]
    _, issued = SessionService(db).create(tenant_id=user.tenant_id, user_id=user.id)
    db.commit()
    _set_auth_cookies(response, token=issued.token, csrf_token=issued.csrf_token)
    return SessionIdentity(user_id=str(user.id), tenant_id=str(user.tenant_id), email=user.email)


@router.get("/me", response_model=SessionIdentity)
def me(
    db: Db,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> SessionIdentity:
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
        _, issued = SessionService(db).rotate(token=session_token)
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
            SessionService(db).revoke(token=session_token)
            db.commit()
        except InvalidSessionError:
            db.rollback()
    _clear_auth_cookies(response)
