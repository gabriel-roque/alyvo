from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings
from app.observability import record

_postgres_connection = None


@lru_cache
def checkpointer():
    global _postgres_connection
    settings = get_settings()
    if settings.app_env == "test" or not settings.langgraph_database_url:
        return MemorySaver()
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection

        _postgres_connection = Connection.connect(
            settings.langgraph_database_url,
            autocommit=True,
            prepare_threshold=0,
        )
        saver = PostgresSaver(_postgres_connection)
        saver.setup()
        record("langgraph.checkpointer", backend="postgres", status="ok")
        return saver
    except Exception as exc:
        # The assistant remains available during a checkpoint-store incident,
        # but readiness and telemetry make the degraded durability visible.
        record(
            "langgraph.checkpointer",
            backend="memory",
            status="degraded",
            reason=type(exc).__name__,
        )
        return MemorySaver()


def close_checkpointer() -> None:
    global _postgres_connection
    if _postgres_connection is not None:
        _postgres_connection.close()
        _postgres_connection = None
