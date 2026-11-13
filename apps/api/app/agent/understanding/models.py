from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.agent.routing import RouteDecision


class AnswerRequirement(StrEnum):
    SERVICE_CONFIRMATION = "service_confirmation"
    PROFESSIONALS = "professionals"
    INSURERS = "insurers"
    AVAILABILITY = "availability"
    APPOINTMENTS = "appointments"
    INSTITUTIONAL_GUIDANCE = "institutional_guidance"


class TurnUnderstanding(BaseModel):
    """Provider-neutral semantic contract consumed by planning.

    It separates what the user expects in the answer from the single primary route. This avoids
    collapsing a compound message into one label and gives validation an explicit checklist.
    """

    model_config = ConfigDict(extra="forbid")

    route: RouteDecision
    requirements: list[AnswerRequirement] = Field(default_factory=list)
    refers_to_previous_result: bool = False
    correction: bool = False
