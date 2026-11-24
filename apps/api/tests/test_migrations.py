from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def run_alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    environment["DATABASE_ADMIN_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def chat_session_columns(database: Path) -> set[str]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute("PRAGMA table_info(chat_sessions)").fetchall()
    return {row[1] for row in rows}


def test_migrations_upgrade_downgrade_and_upgrade_again(tmp_path: Path) -> None:
    database = tmp_path / "migrations.sqlite3"
    database_url = f"sqlite:///{database}"

    run_alembic(database_url, "upgrade", "head")
    assert "context_json" in chat_session_columns(database)

    run_alembic(database_url, "downgrade", "0001_single_clinic")
    assert "context_json" not in chat_session_columns(database)

    run_alembic(database_url, "upgrade", "head")
    assert "context_json" in chat_session_columns(database)
