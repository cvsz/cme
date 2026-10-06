from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from cme_api.db import engine
from cme_api.models import Tenant, User
from cme_api.security import hash_password
from cme_api.session_service import InvalidSessionError, SessionService


def _user(db: Session) -> tuple[Tenant, User]:
    tenant = Tenant(name=f"tenant-{uuid4()}")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"{uuid4()}@example.test",
        password_hash=hash_password("integration-password"),
    )
    db.add(user)
    db.flush()
    return tenant, user


def test_alembic_migrated_auth_session_table_exists():
    with Session(engine) as db:
        count = db.execute(
            text(
                "select count(*) from information_schema.tables where table_name = 'auth_sessions'"
            )
        ).scalar_one()
        assert count == 1


def test_session_rotation_preserves_absolute_expiry():
    with Session(engine) as db, db.begin():
        tenant, user = _user(db)
        service = SessionService(db)
        absolute_expiry = datetime.now(UTC) + timedelta(seconds=30)
        _, issued = service.create(
            tenant_id=tenant.id,
            user_id=user.id,
            expires_at=absolute_expiry,
        )

        replacement, replacement_issued = service.rotate(
            token=issued.token,
            tenant_id=tenant.id,
        )

        assert replacement.expires_at == absolute_expiry
        assert replacement_issued.expires_at == absolute_expiry
        assert replacement.token_digest != replacement_issued.token
        with pytest.raises(InvalidSessionError):
            service.authenticate(token=issued.token, tenant_id=tenant.id)


def test_session_authentication_fails_closed_across_tenants():
    with Session(engine) as db, db.begin():
        tenant, user = _user(db)
        other_tenant = Tenant(name=f"tenant-{uuid4()}")
        db.add(other_tenant)
        db.flush()
        service = SessionService(db)
        _, issued = service.create(tenant_id=tenant.id, user_id=user.id)

        with pytest.raises(InvalidSessionError):
            service.authenticate(token=issued.token, tenant_id=other_tenant.id)

        assert service.authenticate(token=issued.token, tenant_id=tenant.id).user_id == user.id


def test_disabled_user_cannot_reuse_existing_session():
    with Session(engine) as db, db.begin():
        tenant, user = _user(db)
        service = SessionService(db)
        _, issued = service.create(tenant_id=tenant.id, user_id=user.id)
        user.is_active = False
        db.flush()

        with pytest.raises(InvalidSessionError):
            service.authenticate(token=issued.token, tenant_id=tenant.id)
