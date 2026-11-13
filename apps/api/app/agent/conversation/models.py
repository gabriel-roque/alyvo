from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.routing.models import Topic


class AvailabilitySlots(BaseModel):
    """Non-sensitive scheduling preferences collected across chat turns."""

    model_config = ConfigDict(extra="forbid")

    from_date: date | None = None
    to_date: date | None = None
    period: Literal["morning", "afternoon", "evening"] | None = None
    doctor_id: str | None = None
    specialty_id: str | None = None
    unit_id: str | None = None
    insurer_id: str | None = None

    def merge(self, other: AvailabilitySlots) -> AvailabilitySlots:
        return AvailabilitySlots(
            from_date=other.from_date or self.from_date,
            to_date=other.to_date or self.to_date,
            period=other.period or self.period,
            doctor_id=other.doctor_id or self.doctor_id,
            specialty_id=other.specialty_id or self.specialty_id,
            unit_id=other.unit_id or self.unit_id,
            insurer_id=other.insurer_id or self.insurer_id,
        )

    def tool_arguments(self) -> dict[str, str | None]:
        if self.from_date is None:
            raise ValueError("A data é obrigatória para consultar disponibilidade")
        arguments = {
            "from_date": self.from_date.isoformat(),
            "to_date": (self.to_date or self.from_date).isoformat(),
            "period": self.period,
        }
        for key, value in (
            ("doctor_id", self.doctor_id),
            ("specialty_id", self.specialty_id),
            ("unit_id", self.unit_id),
            ("insurer_id", self.insurer_id),
        ):
            if value is not None:
                arguments[key] = value
        return arguments


class DirectoryContext(BaseModel):
    """Non-sensitive references to the last authoritative directory result."""

    model_config = ConfigDict(extra="forbid")

    query: str = ""
    doctor_ids: list[str] = Field(default_factory=list, max_length=20)
    specialties: list[str] = Field(default_factory=list, max_length=20)


class PendingReschedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str
    doctor_id: str


class ConversationContext(BaseModel):
    """Minimal durable state; authenticated identity never belongs here."""

    model_config = ConfigDict(extra="ignore")

    active_topic: Topic | None = None
    availability: AvailabilitySlots = Field(default_factory=AvailabilitySlots)
    directory: DirectoryContext = Field(default_factory=DirectoryContext)
    pending_reschedule: PendingReschedule | None = None
    last_tool: str | None = None
    turn_count: int = Field(default=0, ge=0)

    def next_turn(self) -> ConversationContext:
        return self.model_copy(update={"turn_count": self.turn_count + 1})

    def with_availability(self, slots: AvailabilitySlots) -> ConversationContext:
        return self.model_copy(
            update={
                "active_topic": Topic.AVAILABILITY,
                "availability": self.availability.merge(slots),
            }
        )

    def with_tool(self, tool_name: str) -> ConversationContext:
        return self.model_copy(update={"last_tool": tool_name})

    def with_directory_result(
        self, query: str, doctor_ids: list[str], specialties: list[str]
    ) -> ConversationContext:
        return self.model_copy(
            update={
                "active_topic": Topic.DOCTOR,
                "directory": DirectoryContext(
                    query=query,
                    doctor_ids=doctor_ids[:20],
                    specialties=list(dict.fromkeys(specialties))[:20],
                ),
            }
        )

    def with_pending_reschedule(self, appointment_id: str, doctor_id: str) -> ConversationContext:
        return self.model_copy(
            update={
                "active_topic": Topic.AVAILABILITY,
                "availability": AvailabilitySlots(),
                "pending_reschedule": PendingReschedule(
                    appointment_id=appointment_id,
                    doctor_id=doctor_id,
                ),
            }
        )

    def complete_reschedule(self) -> ConversationContext:
        return self.model_copy(update={"pending_reschedule": None, "active_topic": None})

    def clear_topic(self) -> ConversationContext:
        return self.model_copy(update={"active_topic": None})


class ConversationTurn(BaseModel):
    """A bounded, non-sensitive message made available to response synthesis."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)
