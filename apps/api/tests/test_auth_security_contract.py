from pathlib import Path

AUTH_API = Path(__file__).parents[1] / "cme_api" / "auth_api.py"
SESSION_SERVICE = Path(__file__).parents[1] / "cme_api" / "session_service.py"


def test_auth_cookies_are_secure_and_session_cookie_is_http_only():
    source = AUTH_API.read_text()
    assert 'SESSION_COOKIE = "__Host-cme_session"' in source
    assert "httponly=True" in source
    assert "secure=True" in source
    assert 'samesite="lax"' in source


def test_state_changing_session_routes_require_csrf():
    source = AUTH_API.read_text()
    rotate = source[source.index('def rotate(') : source.index('@router.post("/logout"')]
    logout = source[source.index('def logout(') :]
    assert "_require_csrf(csrf_cookie, csrf_header)" in rotate
    assert "_require_csrf(csrf_cookie, csrf_header)" in logout


def test_session_service_locks_before_revoke_or_rotate():
    source = SESSION_SERVICE.read_text()
    assert "with_for_update(of=AuthSession)" in source
    assert "for_update=True" in source
