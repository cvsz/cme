from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from cme_api.models import AuditEvent


def record_audit_event(
    db: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID | None,
    action: str,
    entity_type: str,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
    )
    db.add(event)
    return event
