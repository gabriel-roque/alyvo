from collections.abc import Generator
from contextvars import ContextVar

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_settings


class Base(DeclarativeBase):
    pass


def options_for(database_url: str) -> dict:
    options: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            options["poolclass"] = StaticPool
    return options


settings = get_settings()
database_url = settings.database_url
admin_database_url = settings.database_admin_url or database_url
engine = create_engine(database_url, **options_for(database_url))
admin_engine = (
    engine
    if admin_database_url == database_url
    else create_engine(admin_database_url, **options_for(admin_database_url))
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
AdminSessionLocal = sessionmaker(bind=admin_engine, autoflush=False, expire_on_commit=False)
tenant_context: ContextVar[str] = ContextVar("tenant_context", default="clinic-alyvo")


@event.listens_for(Session, "after_begin")
def apply_tenant_to_transaction(session, transaction, connection) -> None:
    if connection.dialect.name == "postgresql":
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_context.get()},
        )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        if engine.dialect.name == "postgresql":
            db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_context.get()})
        yield db
    finally:
        db.close()


def create_schema() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=admin_engine)


def set_database_tenant(db: Session, tenant_id: str) -> None:
    tenant_context.set(tenant_id)
    if engine.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": tenant_id})

