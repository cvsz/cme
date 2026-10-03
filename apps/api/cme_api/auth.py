from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    organization_id: UUID | None
    roles: frozenset[str]
    permissions: frozenset[str]


def require_permission(principal: Principal, permission: str) -> Principal:
    if "*" not in principal.permissions and permission not in principal.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return principal
