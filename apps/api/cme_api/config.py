from functools import lru_cache
from urllib.parse import unquote, urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CMe CheerTsuMe' Enterprise Platform API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://cme:cme@localhost:5432/cme"
    redis_url: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(env_prefix="CME_", env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_config(self):
        if self.app_env.lower() != "production":
            return self

        parsed = urlsplit(self.database_url)
        username = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        hostname = (parsed.hostname or "").lower()
        if (
            parsed.scheme not in {"postgresql+psycopg", "postgresql"}
            or not username
            or not password
            or (username == "cme" and password == "cme")
            or password.lower() in {"password", "changeme", "secret", "postgres"}
            or hostname in {"", "localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("production requires a non-default PostgreSQL connection")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
