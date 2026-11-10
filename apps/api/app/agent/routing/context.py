from __future__ import annotations

import re

from app.agent.conversation import ConversationContext
from app.agent.routing.models import Action, Domain, RouteDecision, RouteSource, Topic
from app.agent.routing.rules import normalize

TEMPORAL_TERMS = (
    "hoje",
    "amanha",
    "segunda",
    "terca",
    "quarta",
    "quinta",
    "sexta",
    "sabado",
    "domingo",
    "manha",
    "tarde",
    "noite",
    "outro dia",
    "outra data",
)


def resolve_from_context(
    route: RouteDecision, message: str, context: ConversationContext
) -> RouteDecision:
    if route.domain != Domain.FALLBACK or context.active_topic != Topic.AVAILABILITY:
        return route
    text = normalize(message)
    has_date = bool(re.search(r"\b(?:20\d{2}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2})\b", message))
    if has_date or any(term in text for term in TEMPORAL_TERMS):
        return RouteDecision(
            domain=Domain.SCHEDULING,
            action=Action.SEARCH,
            topic=Topic.AVAILABILITY,
            confidence=0.99,
            conversation_marker=route.conversation_marker,
            source=RouteSource.CONTEXT,
            reason="continued availability collection",
        )
    return route
