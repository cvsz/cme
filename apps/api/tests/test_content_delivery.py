from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from cme_api.content_delivery import (
    InvalidPublicationTransition,
    PublicationContext,
    PublicationState,
    require_utc_schedule,
    transition,
)


def publication():
    return PublicationContext(uuid4(), uuid4(), uuid4(), PublicationState.DRAFT)


def move(item, state):
    return transition(
        item,
        state,
        actor_tenant_id=item.tenant_id,
        actor_organization_id=item.organization_id,
    )


def test_explicit_approval_required_before_queue():
    item = publication()
    with pytest.raises(InvalidPublicationTransition):
        move(item, PublicationState.QUEUED)
    item = move(item, PublicationState.NEEDS_APPROVAL)
    item = move(item, PublicationState.APPROVED)
    assert move(item, PublicationState.QUEUED).state == PublicationState.QUEUED


def test_cross_tenant_and_cross_organization_transition_rejected():
    item = publication()
    for tenant, org in ((uuid4(), item.organization_id), (item.tenant_id, uuid4())):
        with pytest.raises(PermissionError):
            transition(
                item,
                PublicationState.NEEDS_APPROVAL,
                actor_tenant_id=tenant,
                actor_organization_id=org,
            )


def test_original_state_not_mutated():
    item = publication()
    changed = move(item, PublicationState.NEEDS_APPROVAL)
    assert item.state == PublicationState.DRAFT
    assert changed.publication_id == item.publication_id


@pytest.mark.parametrize(
    "terminal",
    [
        PublicationState.PUBLISHED,
        PublicationState.CANCELLED,
        PublicationState.FAILED_TERMINAL,
    ],
)
def test_terminal_states_cannot_transition(terminal):
    item = publication()
    item = PublicationContext(
        item.tenant_id, item.organization_id, item.publication_id, terminal
    )
    with pytest.raises(InvalidPublicationTransition):
        move(item, PublicationState.QUEUED)


def test_ambiguous_provider_response_reconciles_before_retry():
    item = publication()
    for state in [
        PublicationState.NEEDS_APPROVAL,
        PublicationState.APPROVED,
        PublicationState.QUEUED,
        PublicationState.PROCESSING,
        PublicationState.PUBLISHING,
        PublicationState.RECONCILING,
    ]:
        item = move(item, state)
    with pytest.raises(InvalidPublicationTransition):
        move(item, PublicationState.PUBLISHING)
    item = move(item, PublicationState.PUBLISHED)
    assert item.state == PublicationState.PUBLISHED


def test_scheduled_time_must_be_aware_and_future():
    with pytest.raises(ValueError):
        require_utc_schedule(datetime(2040, 1, 1))
    with pytest.raises(ValueError):
        require_utc_schedule(datetime.now(UTC) - timedelta(minutes=1))
    scheduled = datetime.now(UTC) + timedelta(days=2)
    assert require_utc_schedule(scheduled).tzinfo == UTC
