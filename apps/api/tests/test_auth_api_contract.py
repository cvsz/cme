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


def test_session_cookie_uses_host_only_prefix():
    source = AUTH_API.read_text()
    assert 'SESSION_COOKIE = "__Host-cme_session"' in source


def test_login_is_rate_limited_before_password_verification():
    source = AUTH_API.read_text()
    login = source[source.index("def login(") : source.index('@router.get("/me"')]
    assert login.index("_rate_limit_login") < login.index("verify_password")


def test_unknown_email_uses_dummy_password_hash():
    source = AUTH_API.read_text()
    assert "_DUMMY_HASH = hash_password" in source
    assert "verify_password(payload.password, _DUMMY_HASH)" in source


def test_identity_response_disables_caching():
    source = AUTH_API.read_text()
    me = source[source.index("def me(") : source.index('@router.post("/rotate"')]
    assert "_set_no_store(response)" in me
    assert '"Cache-Control"] = "no-store"' in source
