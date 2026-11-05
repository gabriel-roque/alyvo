"""Compatibility path for the retrieval service."""

from app.retrieval.service import (
    AnswerabilityStatus,
    Evidence,
    RetrievalResult,
    local_retrieval_only,
    retrieve,
)

__all__ = [
    "AnswerabilityStatus",
    "Evidence",
    "RetrievalResult",
    "local_retrieval_only",
    "retrieve",
]
