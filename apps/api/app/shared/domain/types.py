from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol


def new_id() -> str:
    return str(uuid.uuid4())


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
