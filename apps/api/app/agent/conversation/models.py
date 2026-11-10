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

    def merge(self, other: AvailabilitySlots) -> AvailabilitySlots:
        return AvailabilitySlots(
            from_date=other.from_date or self.from_date,
            to_date=other.to_date or self.to_date,
            period=other.period or self.period,
        )

    def tool_arguments(self) -> dict[str, str | None]:
        if self.from_date is None:
            raise ValueError("A data é obrigatória para consultar disponibilidade")
        return {
            "from_date": self.from_date.isoformat(),
            "to_date": (self.to_date or self.from_date).isoformat(),
            "period": self.period,
        }


class ConversationContext(BaseModel):
    """Minimal durable state; authenticated identity never belongs here."""

    model_config = ConfigDict(extra="ignore")

    active_topic: Topic | None = None
    availability: AvailabilitySlots = Field(default_factory=AvailabilitySlots)
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

    def clear_topic(self) -> ConversationContext:
        return self.model_copy(update={"active_topic": None})


class ConversationTurn(BaseModel):
    """A bounded, non-sensitive message made available to response synthesis."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)
