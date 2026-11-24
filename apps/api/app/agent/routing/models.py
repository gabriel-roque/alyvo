from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Domain(StrEnum):
    CONVERSATION = "conversation"
    KNOWLEDGE = "knowledge"
    DIRECTORY = "directory"
    SCHEDULING = "scheduling"
    PATIENT = "patient"
    CLINICAL_SAFETY = "clinical_safety"
    SECURITY = "security"
    FALLBACK = "fallback"


class Action(StrEnum):
    GREET = "greet"
    THANK = "thank"
    FAREWELL = "farewell"
    DESCRIBE = "describe"
    SEARCH = "search"
    LIST = "list"
    CREATE = "create"
    CANCEL = "cancel"
    RESCHEDULE = "reschedule"
    REJECT = "reject"
    CLARIFY = "clarify"


class Topic(StrEnum):
    GENERAL = "general"
    DOCTOR = "doctor"
    SPECIALTY = "specialty"
    INSURER = "insurer"
    EXAM = "exam"
    UNIT = "unit"
    AVAILABILITY = "availability"
    OWN_APPOINTMENT = "own_appointment"
    INSTITUTIONAL = "institutional"
    CLINICAL = "clinical"
    UNAUTHORIZED = "unauthorized"
    UNKNOWN = "unknown"


class RiskLevel(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    URGENT = "urgent"


class ConversationMarker(StrEnum):
    GREETING = "greeting"
    THANKS = "thanks"
    FAREWELL = "farewell"


class RouteSource(StrEnum):
    RULE = "rule"
    CONTEXT = "context"
    SEMANTIC = "semantic"
    FALLBACK = "fallback"


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: Domain
    action: Action
    topic: Topic
    confidence: float = Field(ge=0, le=1)
    risk: RiskLevel = RiskLevel.NORMAL
    needs_clarification: bool = False
    reason: str | None = None
    conversation_marker: ConversationMarker | None = None
    secondary_topics: list[Topic] = Field(default_factory=list)
    source: RouteSource = RouteSource.RULE
