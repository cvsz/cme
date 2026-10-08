import pytest
from pydantic import ValidationError

from cme_api.config import Settings


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://cme:cme@postgres:5432/cme",
        "postgresql+psycopg://cme:password@postgres:5432/cme",
        "postgresql+psycopg://cme:strong-password@localhost:5432/cme",
        "postgresql+psycopg://cme@postgres:5432/cme",
    ],
)
def test_production_rejects_unsafe_database_urls(url):
    with pytest.raises(ValidationError, match="production requires"):
        Settings(_env_file=None, app_env="production", database_url=url)


def test_production_accepts_non_default_credentials():
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+psycopg://cme:nondefault-long-secret@postgres:5432/cme",
    )
    assert settings.app_env == "production"


def test_development_retains_local_defaults():
    settings = Settings(_env_file=None, app_env="development")
    assert settings.app_env == "development"
