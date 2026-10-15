"""Schema contract tests for publication persistence (no live provider operations)."""

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from cme_api.db import Base
from cme_api.models import ContentPublication, PublicationOutboxEvent


def test_models_registered_with_metadata():
    assert ContentPublication.__table__ is Base.metadata.tables["content_publications"]
    assert PublicationOutboxEvent.__table__ is Base.metadata.tables[
        "publication_outbox_events"
    ]


def test_publication_scoped_idempotency_and_ownership():
    table = ContentPublication.__table__
    uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("tenant_id", "organization_id", "idempotency_key") in uniques
    assert ("tenant_id", "organization_id", "id") in uniques
    fks = [
        constraint for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]
    assert any(
        constraint.name == "fk_content_publications_organization" for constraint in fks
    )


def test_outbox_foreign_key_rejects_cross_scope_reference():
    table = PublicationOutboxEvent.__table__
    foreign_keys = [
        constraint for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]
    scoped = next(
        constraint
        for constraint in foreign_keys
        if constraint.name == "fk_publication_outbox_publication_scope"
    )
    assert {column.name for column in scoped.columns} == {
        "tenant_id", "organization_id", "publication_id"
    }
    unique = next(
        constraint for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_publication_outbox_event_key"
    )
    assert {column.name for column in unique.columns} == {
        "tenant_id", "organization_id", "event_key"
    }
