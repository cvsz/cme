import logging

import pytest
from pydantic import ValidationError

from cme_api.config import Settings

VALID_DATABASE_URL = (
    "postgresql+psycopg://cme_app:Strong%40Credential%2397-Blue-Maple@postgres:5432/cme"
)
VALID_REDIS_URL = "redis://:Strong%40Redis%2397-Blue-Maple-Cache@redis:6379/0"


def production_settings(**overrides):
    values = {
        "database_url": VALID_DATABASE_URL,
        "redis_url": VALID_REDIS_URL,
    }
    values.update(overrides)
    return Settings(_env_file=None, app_env="production", **values)


def test_production_requires_explicit_database_and_redis_urls():
    with pytest.raises(ValidationError, match="production requires"):
        Settings(_env_file=None, app_env="production", database_url="", redis_url="")


def test_production_rejects_default_database_credentials():
    with pytest.raises(ValidationError, match="production requires"):
        production_settings(database_url="postgresql+psycopg://cme:cme@postgres:5432/cme")

    with pytest.raises(ValidationError, match="production requires"):
        production_settings(
            database_url=(
                "postgresql+psycopg://postgres:Strong%40Credential%2397-Blue-Maple@"
                "postgres:5432/cme"
            )
        )


def test_production_rejects_short_or_placeholder_database_passwords():
    with pytest.raises(ValidationError, match="production requires"):
        production_settings(database_url="postgresql+psycopg://cme:short@postgres:5432/cme")

    with pytest.raises(ValidationError, match="production requires"):
        production_settings(
            database_url=(
                "postgresql+psycopg://cme:Replace%5FMe%5FWith%5FA%5FSecret%5F123@postgres:5432/cme"
            )
        )


def test_production_rejects_invalid_database_urls():
    with pytest.raises(ValidationError, match="production requires"):
        production_settings(database_url="mysql://cme:strong@postgres:5432/cme")

    with pytest.raises(ValidationError, match="production requires"):
        production_settings(database_url="postgresql+psycopg://cme:strong@[::1:5432/cme")

    with pytest.raises(ValidationError, match="production requires"):
        production_settings(database_url="postgresql+psycopg://cme:strong@postgres:5432")


def test_production_accepts_percent_encoded_strong_credentials():
    settings = production_settings()
    assert settings.app_env == "production"
    assert settings.database_url.get_secret_value() == VALID_DATABASE_URL


def test_production_rejects_percent_encoded_default_credentials():
    with pytest.raises(ValidationError, match="production requires"):
        production_settings(database_url="postgresql+psycopg://cme:%63me@postgres:5432/cme")


def test_production_requires_a_valid_nonlocal_redis_url():
    with pytest.raises(ValidationError, match="production requires"):
        production_settings(redis_url="redis://localhost:6379/0")

    with pytest.raises(ValidationError, match="production requires"):
        production_settings(redis_url="http://redis:6379/0")


@pytest.mark.parametrize("environment", ["prod", "staging", "Production ", ""])
def test_invalid_environment_values_are_rejected(environment):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env=environment)


def test_development_retains_safe_local_defaults(monkeypatch):
    # CI supplies CME_DATABASE_URL for its PostgreSQL service; isolate the defaults test.
    monkeypatch.delenv("CME_DATABASE_URL", raising=False)
    monkeypatch.delenv("CME_REDIS_URL", raising=False)
    settings = Settings(_env_file=None, app_env="development")
    assert settings.app_env == "development"
    assert settings.database_url.get_secret_value().endswith("@localhost:5432/cme")
    assert settings.redis_url.get_secret_value() == "redis://localhost:6379/0"


def test_production_validation_errors_and_logs_redact_database_secrets(caplog):
    marker = "Synthetic-Only-Secret-Value-83%21"
    logger = logging.getLogger("cme_api.config_test")

    with caplog.at_level(logging.ERROR, logger="cme_api.config_test"):
        try:
            Settings(
                _env_file=None,
                app_env="production",
                database_url=(f"postgresql+psycopg://cme_app:{marker}@localhost:5432/cme"),
                redis_url=VALID_REDIS_URL,
            )
        except ValidationError:
            logger.exception("Production configuration validation failed")
        else:
            pytest.fail("weak synthetic credential unexpectedly passed production validation")

    assert marker not in caplog.text
    assert "Production configuration validation failed" in caplog.text
