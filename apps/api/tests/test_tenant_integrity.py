from pathlib import Path

MIGRATION = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "0002_tenant_integrity.py"
)


def test_tenant_integrity_migration_is_forward_only_from_core():
    source = MIGRATION.read_text()
    assert 'down_revision = "0001_cme_core"' in source
    assert "fk_chart_accounts_organization" in source
    assert '["tenant_id", "organization_id"]' in source
    assert '["tenant_id", "id"]' in source


def test_all_tenant_owned_core_tables_get_database_foreign_keys():
    source = MIGRATION.read_text()
    for constraint in (
        "fk_organizations_tenant",
        "fk_users_tenant",
        "fk_audit_events_tenant",
        "fk_inventory_movements_tenant",
    ):
        assert constraint in source


def test_audit_actor_cannot_cross_tenant_boundary():
    source = MIGRATION.read_text()
    assert "fk_audit_events_actor" in source
    assert '["tenant_id", "actor_user_id"]' in source
