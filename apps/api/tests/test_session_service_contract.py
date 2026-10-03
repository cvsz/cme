from pathlib import Path

SERVICE = Path(__file__).parents[1] / "cme_api" / "session_service.py"


def test_session_service_never_queries_plaintext_token():
    source = SERVICE.read_text()
    assert "AuthSession.token_digest == digest" in source
    assert "AuthSession.token_digest == token" not in source


def test_rotation_revokes_predecessor_before_issuing_replacement():
    source = SERVICE.read_text()
    revoke = source.index("previous.revoked_at = datetime.now(UTC)")
    create = source.index("record, issued = self.create(")
    assert revoke < create


def test_tenant_filter_is_supported_for_authentication():
    source = SERVICE.read_text()
    assert "AuthSession.tenant_id == tenant_id" in source
