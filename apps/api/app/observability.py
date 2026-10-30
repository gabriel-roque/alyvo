from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

correlation_id_context: ContextVar[str] = ContextVar(
    "correlation_id_context", default="background"
)
logger = logging.getLogger("alyvo.telemetry")


def correlation_id() -> str:
    return correlation_id_context.get()


def record(event: str, **fields) -> None:
    safe = {
        key: value
        for key, value in fields.items()
        if key not in {"cpf", "content", "document", "raw_ocr", "password", "token"}
    }
    logger.info(
        json.dumps(
            {"event": event, "correlation_id": correlation_id(), **safe},
            ensure_ascii=False,
            default=str,
        )
    )


@contextmanager
def operation(event: str, **fields) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        record(
            event,
            status="error",
            error_type=type(exc).__name__,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            **fields,
        )
        raise
    record(
        event,
        status="ok",
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
        **fields,
    )

