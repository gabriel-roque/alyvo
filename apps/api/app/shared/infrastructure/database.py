from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bootstrap.config import get_settings


def _engine_options(url: str) -> dict:
    options: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            options["poolclass"] = StaticPool
    return options


settings = get_settings()
database_url = settings.database_url
admin_database_url = settings.database_admin_url or database_url
engine = create_engine(database_url, **_engine_options(database_url))
admin_engine = (
    engine
    if admin_database_url == database_url
    else create_engine(admin_database_url, **_engine_options(admin_database_url))
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
AdminSessionLocal = sessionmaker(bind=admin_engine, autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
