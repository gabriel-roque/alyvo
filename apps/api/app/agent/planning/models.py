from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.agent.conversation import ConversationContext


class PlanKind(StrEnum):
    DIRECT = "direct"
    CLARIFICATION = "clarification"
    TOOL = "tool"
    RAG = "rag"
    HYBRID = "hybrid"
    REJECT = "reject"


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, object] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PlanKind
    steps: list[PlanStep] = Field(default_factory=list)
    response: dict[str, object] | None = None
    reason_codes: list[str] = Field(default_factory=list)
    context: ConversationContext = Field(default_factory=ConversationContext)

    @property
    def first_step(self) -> PlanStep | None:
        return self.steps[0] if self.steps else None
