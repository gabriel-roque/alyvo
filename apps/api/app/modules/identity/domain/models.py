from dataclasses import dataclass
from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    RECEPTIONIST = "receptionist"
    PATIENT = "patient"


@dataclass(frozen=True)
class Actor:
    id: str
    role: UserRole
    name: str | None = None

    @property
    def is_staff(self) -> bool:
        return self.role in {UserRole.ADMIN, UserRole.RECEPTIONIST}
