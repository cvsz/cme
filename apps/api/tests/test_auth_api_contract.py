from pathlib import Path

AUTH_API = Path(__file__).parents[1] / "cme_api" / "auth_api.py"


def test_auth_cookie_is_http_only_secure_and_same_site():
    source = AUTH_API.read_text()
    start = source.index("response.set_cookie(")
    end = source.index("response.set_cookie(", start + 1)
    session_cookie = source[start:end]
    assert "httponly=True" in session_cookie
    assert "secure=True" in session_cookie
    assert 'samesite="lax"' in session_cookie


def test_state_changing_session_routes_require_constant_time_csrf_check():
    source = AUTH_API.read_text()
    assert "secrets.compare_digest" in source
    rotate = source[source.index("def rotate(") : source.index('@router.post("/logout"')]
    logout = source[source.index("def logout(") :]
    assert "_require_csrf(csrf_cookie, csrf_header)" in rotate
    assert "_require_csrf(csrf_cookie, csrf_header)" in logout


def test_login_rejects_ambiguous_cross_tenant_email():
    source = AUTH_API.read_text()
    assert "if len(matches) != 1:" in source
    assert "invalid credentials" in source


def test_identity_is_resolved_from_persisted_session():
    source = AUTH_API.read_text()
    assert "SessionService(db).authenticate(token=token)" in source
    me = source[source.index("def me(") : source.index('@router.post("/rotate"')]
    assert "tenant_id:" not in me
