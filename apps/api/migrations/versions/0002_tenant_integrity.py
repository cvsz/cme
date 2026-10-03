"""Enforce tenant-scoped referential integrity.

Revision ID: 0002_tenant_integrity
Revises: 0001_cme_core
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_tenant_integrity"
down_revision = "0001_cme_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_tenants_id", "tenants", ["id"])
    op.create_unique_constraint("uq_users_tenant_id_id", "users", ["tenant_id", "id"])

    op.create_foreign_key(
        "fk_organizations_tenant",
        "organizations",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_users_tenant",
        "users",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_audit_events_tenant",
        "audit_events",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_audit_events_actor",
        "audit_events",
        "users",
        ["tenant_id", "actor_user_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_chart_accounts_organization",
        "chart_accounts",
        "organizations",
        ["tenant_id", "organization_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inventory_movements_tenant",
        "inventory_movements",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_inventory_movements_tenant", "inventory_movements", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_chart_accounts_organization", "chart_accounts", type_="foreignkey"
    )
    op.drop_constraint("fk_audit_events_actor", "audit_events", type_="foreignkey")
    op.drop_constraint("fk_audit_events_tenant", "audit_events", type_="foreignkey")
    op.drop_constraint("fk_users_tenant", "users", type_="foreignkey")
    op.drop_constraint("fk_organizations_tenant", "organizations", type_="foreignkey")
    op.drop_constraint("uq_users_tenant_id_id", "users", type_="unique")
    op.drop_constraint("uq_tenants_id", "tenants", type_="unique")
