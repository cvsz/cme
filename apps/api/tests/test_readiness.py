from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from cme_api import main


def test_liveness_does_not_touch_database(monkeypatch):
    def fail_if_called():
        raise AssertionError("liveness must not access dependencies")

    monkeypatch.setattr(main, "SessionLocal", fail_if_called)
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class FakeResult:
    def __init__(self, revision):
        self.revision = revision

    def scalar_one(self):
        return self.revision


def test_readiness_checks_schema_revision(monkeypatch):
    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement):
            assert str(statement) == "SELECT version_num FROM alembic_version"
            return FakeResult(main.EXPECTED_SCHEMA_REVISION)

    monkeypatch.setattr(main, "SessionLocal", FakeSession)
    response = TestClient(main.app).get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readiness_fails_closed_when_database_is_unavailable(monkeypatch):
    class BrokenSession:
        def __enter__(self):
            raise OperationalError("SELECT 1", {}, Exception("offline"))

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(main, "SessionLocal", BrokenSession)
    response = TestClient(main.app).get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable or schema not initialized"}


def test_readiness_fails_closed_when_schema_revision_is_stale(monkeypatch):
    class StaleSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _statement):
            return FakeResult("0003_auth_sessions")

    monkeypatch.setattr(main, "SessionLocal", StaleSession)
    response = TestClient(main.app).get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "database schema revision mismatch"}
