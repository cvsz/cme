"""Pure content publication lifecycle policy.

This module is not a publishing worker. Persistence, authorization, provider consent,
outbox delivery and reconciliation must be implemented by subsequent vertical slices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class PublicationState(StrEnum):
    DRAFT = "draft"
    NEEDS_APPROVAL = "needs_approval"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    QUEUED = "queued"
    PROCESSING = "processing"
    PUBLISHING = "publishing"
    RECONCILING = "reconciling"
    PUBLISHED = "published"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"
    CANCELLED = "cancelled"


_ALLOWED: dict[PublicationState, frozenset[PublicationState]] = {
    PublicationState.DRAFT: frozenset(
        {PublicationState.NEEDS_APPROVAL, PublicationState.CANCELLED}
    ),
    PublicationState.NEEDS_APPROVAL: frozenset(
        {PublicationState.APPROVED, PublicationState.DRAFT, PublicationState.CANCELLED}
    ),
    PublicationState.APPROVED: frozenset(
        {PublicationState.SCHEDULED, PublicationState.QUEUED, PublicationState.CANCELLED}
    ),
    PublicationState.SCHEDULED: frozenset({PublicationState.QUEUED, PublicationState.CANCELLED}),
    PublicationState.QUEUED: frozenset({PublicationState.PROCESSING, PublicationState.CANCELLED}),
    PublicationState.PROCESSING: frozenset(
        {
            PublicationState.PUBLISHING,
            PublicationState.FAILED_RETRYABLE,
            PublicationState.FAILED_TERMINAL,
        }
    ),
    PublicationState.PUBLISHING: frozenset(
        {PublicationState.PUBLISHED, PublicationState.RECONCILING, PublicationState.FAILED_TERMINAL}
    ),
    PublicationState.RECONCILING: frozenset(
        {
            PublicationState.PUBLISHED,
            PublicationState.FAILED_RETRYABLE,
            PublicationState.FAILED_TERMINAL,
        }
    ),
    PublicationState.FAILED_RETRYABLE: frozenset(
        {PublicationState.QUEUED, PublicationState.RECONCILING, PublicationState.FAILED_TERMINAL}
    ),
    PublicationState.PUBLISHED: frozenset(),
    PublicationState.FAILED_TERMINAL: frozenset(),
    PublicationState.CANCELLED: frozenset(),
}


class InvalidPublicationTransition(ValueError):
    """A workflow operation would violate publication lifecycle policy."""


@dataclass(frozen=True, slots=True)
class PublicationContext:
    tenant_id: UUID
    organization_id: UUID
    publication_id: UUID
    state: PublicationState


def transition(
    publication: PublicationContext,
    next_state: PublicationState,
    *,
    actor_tenant_id: UUID,
    actor_organization_id: UUID,
) -> PublicationContext:
    """Validate scope and lifecycle. Callers must separately enforce actor RBAC."""
    if (
        actor_tenant_id != publication.tenant_id
        or actor_organization_id != publication.organization_id
    ):
        raise PermissionError("publication scope mismatch")
    if next_state not in _ALLOWED[publication.state]:
        raise InvalidPublicationTransition(
            f"invalid publication transition: {publication.state} -> {next_state}"
        )
    return PublicationContext(
        tenant_id=publication.tenant_id,
        organization_id=publication.organization_id,
        publication_id=publication.publication_id,
        state=next_state,
    )


def require_utc_schedule(when: datetime) -> datetime:
    """Reject naive/past or non-UTC schedule times; store authoritative UTC time."""
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("scheduled time must be timezone-aware")
    now = datetime.now(UTC)
    normalized = when.astimezone(UTC)
    if normalized <= now:
        raise ValueError("scheduled time must be in the future")
    return normalized
