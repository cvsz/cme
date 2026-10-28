"""Add tenant-scoped content publication and transactional outbox foundation.

Revision ID: 0005_content_publication
Revises: 0004_accounting_journal
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_content_publication"
down_revision = "0004_accounting_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "id",
            name="uq_content_publications_scope",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_content_publications_idempotency",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "organization_id"],
            ["organizations.tenant_id", "organizations.id"],
            name="fk_content_publications_organization",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_content_publications_tenant_id", "content_publications", ["tenant_id"])
    op.create_index(
        "ix_content_publications_organization_id",
        "content_publications",
        ["organization_id"],
    )
    op.create_table(
        "publication_outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("publication_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "event_key",
            name="uq_publication_outbox_event_key",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "organization_id", "publication_id"],
            [
                "content_publications.tenant_id",
                "content_publications.organization_id",
                "content_publications.id",
            ],
            name="fk_publication_outbox_publication_scope",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_publication_outbox_events_tenant_id",
        "publication_outbox_events",
        ["tenant_id"],
    )
    op.create_index(
        "ix_publication_outbox_events_organization_id",
        "publication_outbox_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_publication_outbox_events_publication_id",
        "publication_outbox_events",
        ["publication_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_publication_outbox_events_publication_id", table_name="publication_outbox_events"
    )
    op.drop_index(
        "ix_publication_outbox_events_organization_id", table_name="publication_outbox_events"
    )
    op.drop_index(
        "ix_publication_outbox_events_tenant_id", table_name="publication_outbox_events"
    )
    op.drop_table("publication_outbox_events")
    op.drop_index(
        "ix_content_publications_organization_id", table_name="content_publications"
    )
    op.drop_index("ix_content_publications_tenant_id", table_name="content_publications")
    op.drop_table("content_publications")
