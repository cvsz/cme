import re
from functools import lru_cache
from ipaddress import ip_address
from typing import Literal
from urllib.parse import SplitResult, unquote, urlsplit

from pydantic import SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DATABASE_URL = "postgresql+psycopg://cme:cme@localhost:5432/cme"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_WEAK_PASSWORDS = {"cme", "changeme", "password", "postgres", "replace_me", "secret"}
_WEAK_USERS = {"admin", "cme", "postgres", "root"}
_PLACEHOLDER_MARKERS = ("change_me", "changeme", "example", "replace_me", "your_password")


def _is_loopback(hostname: str) -> bool:
    normalized = hostname.casefold().rstrip(".")
    if normalized in {"localhost", "ip6-localhost"}:
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _has_strong_password(password: str) -> bool:
    normalized = password.casefold()
    categories = sum(
        (
            any(character.islower() for character in password),
            any(character.isupper() for character in password),
            any(character.isdigit() for character in password),
            any(not character.isalnum() for character in password),
        )
    )
    return (
        len(password) >= 24
        and categories >= 3
        and normalized not in _WEAK_PASSWORDS
        and not any(marker in normalized for marker in _PLACEHOLDER_MARKERS)
    )


def _parse_url(value: SecretStr) -> SplitResult:
    raw_url = value.get_secret_value()
    if any(character.isspace() for character in raw_url) or _INVALID_PERCENT_ESCAPE.search(raw_url):
        raise ValueError("invalid connection URL")
    return urlsplit(raw_url)


def _validate_production_database_url(value: SecretStr) -> None:
    try:
        database = _parse_url(value)
        db_username = unquote(database.username or "")
        db_password = unquote(database.password or "")
        db_hostname = database.hostname or ""
        _ = database.port
    except ValueError:
        raise ValueError("production requires a valid PostgreSQL connection") from None

    if (
        database.scheme not in {"postgresql+psycopg", "postgresql"}
        or not db_username
        or db_username.casefold() in _WEAK_USERS
        or not _has_strong_password(db_password)
        or not db_hostname
        or _is_loopback(db_hostname)
        or not database.path.strip("/")
    ):
        raise ValueError("production requires a valid PostgreSQL connection")


def _validate_production_redis_url(value: SecretStr) -> None:
    try:
        redis = _parse_url(value)
        redis_hostname = redis.hostname or ""
        _ = redis.port
    except ValueError:
        raise ValueError("production requires a valid Redis connection") from None

    if (
        redis.scheme not in {"redis", "rediss"}
        or not redis_hostname
        or _is_loopback(redis_hostname)
    ):
        raise ValueError("production requires a valid Redis connection")


class Settings(BaseSettings):
    app_name: str = "CMe CheerTsuMe' Enterprise Platform API"
    app_env: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    database_url: SecretStr = SecretStr(_DEFAULT_DATABASE_URL)
    redis_url: SecretStr = SecretStr(_DEFAULT_REDIS_URL)

    model_config = SettingsConfigDict(env_prefix="CME_", env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        if info.data.get("app_env") == "production":
            _validate_production_database_url(value)
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        if info.data.get("app_env") == "production":
            _validate_production_redis_url(value)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
