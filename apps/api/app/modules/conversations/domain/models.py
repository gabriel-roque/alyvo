from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationId:
    value: str
