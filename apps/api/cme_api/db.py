from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from cme_api.config import get_settings


class Base(DeclarativeBase):
    pass


def _url() -> str:
    return get_settings().database_url.get_secret_value()


engine = create_engine(_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
