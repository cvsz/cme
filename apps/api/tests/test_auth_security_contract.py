from pathlib import Path

AUTH_API = Path(__file__).parents[1] / "cme_api" / "auth_api.py"
SESSION_SERVICE = Path(__file__).parents[1] / "cme_api" / "session_service.py"


def _function_source(source: str, name: str, next_name: str | None = None) -> str:
    start = source.index(f"def {name}(")
    if next_name is None:
        return source[start:]
    return source[start : source.index(f"def {next_name}(", start)]


def test_auth_cookies_are_secure_and_session_cookie_is_http_only():
    source = AUTH_API.read_text()
    setter = _function_source(source, "_set_auth_cookies", "_clear_auth_cookies")
    session_call, csrf_call = setter.split("response.set_cookie(", 2)[1:]
    assert "SESSION_COOKIE, token, httponly=True, secure=True" in session_call
    assert "CSRF_COOKIE, csrf_token, httponly=False, secure=True" in csrf_call
    assert 'samesite="lax"' in session_call
    assert 'samesite="lax"' in csrf_call


def test_state_changing_session_routes_require_csrf():
    source = AUTH_API.read_text()
    rotate = _function_source(source, "rotate", "logout")
    logout = _function_source(source, "logout")
    assert "_require_csrf(csrf_cookie, csrf_header)" in rotate
    assert "_require_csrf(csrf_cookie, csrf_header)" in logout


def test_revoke_and_rotate_lock_predecessor_independently():
    source = SESSION_SERVICE.read_text()
    revoke = _function_source(source, "revoke", "rotate")
    rotate = _function_source(source, "rotate")
    assert "for_update=True" in revoke
    assert "for_update=True" in rotate
