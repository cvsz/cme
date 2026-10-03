from datetime import UTC, datetime, timedelta

from cme_api.sessions import csrf_matches, issue_session, session_is_active, token_digest


def test_session_token_is_stored_as_digest():
    issued = issue_session()
    assert issued.token != issued.token_digest
    assert token_digest(issued.token) == issued.token_digest
    assert len(issued.token_digest) == 64


def test_session_expiry_and_revocation_are_enforced():
    now = datetime.now(UTC)
    assert session_is_active(expires_at=now + timedelta(minutes=1), revoked_at=None, now=now)
    assert not session_is_active(expires_at=now, revoked_at=None, now=now)
    assert not session_is_active(expires_at=now + timedelta(minutes=1), revoked_at=now, now=now)


def test_csrf_requires_matching_cookie_and_header():
    assert csrf_matches(cookie_token="secret", header_token="secret")
    assert not csrf_matches(cookie_token="secret", header_token="different")
    assert not csrf_matches(cookie_token=None, header_token="secret")
