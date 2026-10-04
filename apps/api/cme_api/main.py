from fastapi import FastAPI

from cme_api.auth_api import router as auth_router
from cme_api.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(auth_router, prefix=settings.api_prefix)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["operations"])
def readiness() -> dict[str, str]:
    # Dependency probes will be added with PostgreSQL/Redis wiring.
    return {"status": "ready", "environment": settings.app_env}
