import hashlib
from pathlib import Path

from sqlalchemy import text

from app.db import admin_engine


def apply_migrations() -> None:
    if admin_engine.dialect.name != "postgresql":
        return
    migration_dir = Path(__file__).resolve().parents[1] / "migrations"
    with admin_engine.begin() as connection:
        connection.execute(text("SELECT set_config('app.tenant_id', '*', true)"))
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        for path in sorted(migration_dir.glob("*.sql")):
            sql = path.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            existing = connection.execute(
                text("SELECT checksum FROM schema_migrations WHERE name = :name"),
                {"name": path.name},
            ).scalar_one_or_none()
            if existing:
                if existing != checksum:
                    raise RuntimeError(f"Migration já aplicada foi alterada: {path.name}")
                continue
            connection.exec_driver_sql(sql)
            connection.execute(
                text("INSERT INTO schema_migrations(name, checksum) VALUES (:name, :checksum)"),
                {"name": path.name, "checksum": checksum},
            )
