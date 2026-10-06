"""Add tenant-scoped immutable accounting journal.

Revision ID: 0004_accounting_journal
Revises: 0003_auth_sessions
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_accounting_journal"
down_revision = "0003_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_chart_accounts_scope", "chart_accounts", ["tenant_id", "organization_id", "id"]
    )
    op.create_table(
        "journal_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "organization_id", "idempotency_key",
            name="uq_journal_entries_idempotency",
        ),
        sa.UniqueConstraint(
            "tenant_id", "organization_id", "id", name="uq_journal_entries_scope"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "organization_id"],
            ["organizations.tenant_id", "organizations.id"],
            name="fk_journal_entries_organization",
            ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "journal_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("debit", sa.Numeric(18, 2), nullable=False),
        sa.Column("credit", sa.Numeric(18, 2), nullable=False),
        sa.CheckConstraint("debit >= 0 AND credit >= 0", name="ck_journal_lines_nonnegative"),
        sa.CheckConstraint(
            "(debit = 0 AND credit > 0) OR (credit = 0 AND debit > 0)",
            name="ck_journal_lines_one_sided",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "organization_id", "entry_id"],
            ["journal_entries.tenant_id", "journal_entries.organization_id", "journal_entries.id"],
            name="fk_journal_lines_entry",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "organization_id", "account_id"],
            ["chart_accounts.tenant_id", "chart_accounts.organization_id", "chart_accounts.id"],
            name="fk_journal_lines_account",
            ondelete="RESTRICT",
        ),
    )
    op.execute("""
        CREATE FUNCTION reject_journal_mutation() RETURNS trigger AS $
        BEGIN
            RAISE EXCEPTION 'posted journals are immutable';
        END;
        $ LANGUAGE plpgsql
    """)
    for table in ("journal_entries", "journal_lines"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable "
            f"BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_journal_mutation()"
        )


def downgrade() -> None:
    for table in ("journal_lines", "journal_entries"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_journal_mutation()")
    op.drop_table("journal_lines")
    op.drop_table("journal_entries")
    op.drop_constraint("uq_chart_accounts_scope", "chart_accounts", type_="unique")
