from fastapi import FastAPI

from cme_api.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["operations"])
def readiness() -> dict[str, str]:
    # Dependency probes will be added with PostgreSQL/Redis wiring.
    return {"status": "ready", "environment": settings.app_env}
