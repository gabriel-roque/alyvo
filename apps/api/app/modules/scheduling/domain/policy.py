from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class CancellationPolicy:
    notice_hours: int

    def allows(self, starts_at: datetime, now: datetime, staff_override: bool = False) -> bool:
        return (
            staff_override
            or self.notice_hours == 0
            or now <= starts_at - timedelta(hours=self.notice_hours)
        )
