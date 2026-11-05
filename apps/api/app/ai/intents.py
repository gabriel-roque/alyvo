"""Compatibility imports for the pre-rewrite module path."""

from app.agent.routing import (
    Action,
    Domain,
    IntentClassification,
    RiskLevel,
    RouteDecision,
    Topic,
    deterministic_classification,
)

__all__ = [
    "Action",
    "Domain",
    "IntentClassification",
    "RiskLevel",
    "RouteDecision",
    "Topic",
    "deterministic_classification",
]
