from dataclasses import dataclass
from enum import StrEnum


class Answerability(StrEnum):
    SUPPORTED = "supported"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class Evidence:
    id: str
    content: str
    title: str
    source: str
    score: float


@dataclass(frozen=True)
class RetrievalResult:
    evidence: tuple[Evidence, ...]
    confidence: float
    strategy: str
    answerability: Answerability
