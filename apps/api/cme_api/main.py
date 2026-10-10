from fastapi import FastAPI, HTTPException
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from cme_api.auth_api import router as auth_router
from cme_api.config import get_settings
from cme_api.db import SessionLocal
from cme_api.observability import RequestObservabilityMiddleware

EXPECTED_SCHEMA_REVISION = "0004_accounting_journal"

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(RequestObservabilityMiddleware)
app.include_router(auth_router, prefix=settings.api_prefix)


def _new_redis_client() -> Redis:
    return Redis.from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def _check_redis() -> None:
    client = None
    try:
        client = _new_redis_client()
        if not client.ping():
            raise RedisError("Redis PING returned an unexpected response")
    except (RedisError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="redis unavailable") from exc
    finally:
        if client is not None:
            client.close()


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["operations"])
def readiness() -> dict[str, object]:
    try:
        with SessionLocal() as db:
            revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    except SQLAlchemyError as exc:
        detail = "database unavailable or schema not initialized"
        raise HTTPException(status_code=503, detail=detail) from exc
    if revision != EXPECTED_SCHEMA_REVISION:
        raise HTTPException(status_code=503, detail="database schema revision mismatch")
    _check_redis()
    return {
        "status": "ready",
        "environment": settings.app_env,
        "schema_revision": revision,
        "dependencies": {"database": "ready", "redis": "ready"},
    }
