from datetime import datetime

from pydantic import Field

from app.agent.tools.models import ToolArgumentsUnion, ToolResult
from app.api.schemas.common import StrictModel


class SessionResponse(StrictModel):
    id: str
    created_at: datetime
    expires_at: datetime


class MessageCreate(StrictModel):
    content: str = Field(min_length=1, max_length=4000)


class ActionCreate(StrictModel):
    tool: str
    arguments: ToolArgumentsUnion


class ConfirmationBody(StrictModel):
    accepted: bool = True


class Citation(StrictModel):
    title: str
    source: str
    excerpt: str


class Suggestion(StrictModel):
    label: str
    message: str


class ConfirmationRequest(StrictModel):
    id: str
    tool: str
    summary: str


class ToolCallView(StrictModel):
    name: str


class PendingTool(StrictModel):
    name: str
    arguments: ToolArgumentsUnion


class ChatResponse(StrictModel):
    answer: str
    intent: str
    confidence: float
    citations: list[Citation] = Field(default_factory=list)
    auth_required: bool = False
    confirmation_request: ConfirmationRequest | None = None
    tool_result: ToolResult | None = None
    tool_call: ToolCallView | None = None
    suggestions: list[Suggestion] = Field(default_factory=list)
    pending_tool: PendingTool | None = None
