from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(StrictRequest):
    tenant_id: str = "clinic-alyvo"


class MessageCreate(StrictRequest):
    content: str = Field(min_length=1, max_length=4000)


class ActionCreate(StrictRequest):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ConfirmationBody(StrictRequest):
    accepted: bool


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    source: str
    excerpt: str


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    tool: str
    summary: str


class ToolCallResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class Suggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    message: str


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    items: list[dict[str, Any]] | None = None
    appointment: dict[str, Any] | None = None
    timezone: str | None = None
    total: int | None = None
    has_more: bool | None = None
    query_summary: str | None = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    answer: str
    intent: str
    confidence: float = Field(ge=0, le=1)
    citations: list[Citation] = Field(default_factory=list)
    auth_required: bool = False
    confirmation_request: ConfirmationRequest | None = None
    tool_result: ToolResult | None = None
    tool_call: ToolCallResponse | None = None
    suggestions: list[Suggestion] = Field(default_factory=list)
    resolved_request: dict[str, Any] | None = None


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    expires_at: datetime
