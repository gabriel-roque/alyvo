from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai.graph import run_graph


def run_agent(
    db: Session,
    tenant_id: str,
    identity: dict[str, Any] | None,
    message: str,
    history: list[dict[str, Any]] | None = None,
    session_state: dict[str, Any] | None = None,
    thread_id: str = "anonymous",
) -> dict[str, Any]:
    return run_graph(
        db,
        tenant_id,
        identity,
        message,
        history,
        session_state,
        thread_id,
    )
