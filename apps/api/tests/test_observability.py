import logging

from fastapi.testclient import TestClient

from cme_api.main import app


def test_request_id_is_returned_and_logged_without_sensitive_headers(caplog):
    caplog.set_level(logging.INFO, logger="cme.http")
    response = TestClient(app).get(
        "/health",
        headers={
            "x-request-id": "req-test-123",
            "authorization": "Bearer never-log-me",
            "cookie": "session=never-log-me",
        },
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-test-123"
    output = caplog.text
    assert "req-test-123" in output
    assert "never-log-me" not in output
    assert "authorization" not in output.lower()
    assert "cookie" not in output.lower()
