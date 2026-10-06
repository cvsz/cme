from fastapi import FastAPI, HTTPException
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


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["operations"])
def readiness() -> dict[str, str]:
    try:
        with SessionLocal() as db:
            revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable or schema not initialized") from exc
    if revision != EXPECTED_SCHEMA_REVISION:
        raise HTTPException(status_code=503, detail="database schema revision mismatch")
    return {"status": "ready", "environment": settings.app_env}
