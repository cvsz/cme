from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from cme_api import auth_api


def test_login_rate_limit_hashes_identity_and_caps_attempts(monkeypatch):
    auth_api._login_attempts.clear()
    monkeypatch.setattr(auth_api, "_LOGIN_MAX_BUCKETS", 1)
    request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.10"))

    for _ in range(auth_api._LOGIN_MAX_ATTEMPTS):
        auth_api._rate_limit_login(request, "Person@example.invalid")

    bucket_key = next(iter(auth_api._login_attempts))
    assert "Person@example.invalid" not in bucket_key
    with pytest.raises(HTTPException) as error:
        auth_api._rate_limit_login(request, "Person@example.invalid")
    assert error.value.status_code == 429

    with pytest.raises(HTTPException) as error:
        auth_api._rate_limit_login(request, "another@example.invalid")
    assert error.value.status_code == 429
    assert len(auth_api._login_attempts) == 1
    auth_api._login_attempts.clear()


def test_expired_login_buckets_are_reclaimed(monkeypatch):
    auth_api._login_attempts.clear()
    monkeypatch.setattr(auth_api, "_LOGIN_MAX_BUCKETS", 1)
    clock = iter((0.0, auth_api._LOGIN_WINDOW_SECONDS + 1.0))
    monkeypatch.setattr(auth_api.time, "monotonic", lambda: next(clock))
    request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.11"))

    auth_api._rate_limit_login(request, "first@example.invalid")
    auth_api._rate_limit_login(request, "second@example.invalid")

    assert len(auth_api._login_attempts) == 1
    auth_api._login_attempts.clear()


def test_login_email_length_is_bounded():
    with pytest.raises(ValidationError):
        auth_api.LoginRequest(email="a" * 255, password="valid-test-password")
