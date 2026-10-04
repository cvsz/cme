from pathlib import Path

SERVICE = Path(__file__).parents[1] / "cme_api" / "session_service.py"


def test_session_service_never_queries_plaintext_token():
    source = SERVICE.read_text()
    assert "AuthSession.token_digest == digest" in source
    assert "AuthSession.token_digest == token" not in source


def test_rotation_locks_predecessor_before_issuing_replacement():
    source = SERVICE.read_text()
    lock = source.index("with_for_update(of=AuthSession)")
    rotate = source.index("previous = self._authenticate(")
    create = source.index("record, issued = self.create(", rotate)
    assert lock < rotate < create
    assert "for_update=True" in source[rotate:create]


def test_authentication_rejects_disabled_users():
    source = SERVICE.read_text()
    assert ".join(" in source
    assert "User.is_active.is_(True)" in source


def test_tenant_filter_is_supported_for_authentication():
    source = SERVICE.read_text()
    assert "AuthSession.tenant_id == tenant_id" in source
