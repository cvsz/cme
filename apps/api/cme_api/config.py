from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CMe CheerTsuMe' Enterprise Platform API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://cme:cme@localhost:5432/cme"
    redis_url: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(env_prefix="CME_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
