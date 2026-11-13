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
    text = normalize(message)
    has_date = bool(re.search(r"\b(?:20\d{2}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2})\b", message))
    has_temporal_preference = has_date or any(term in text for term in TEMPORAL_TERMS)
    if context.pending_reschedule is not None and has_temporal_preference:
        return RouteDecision(
            domain=Domain.SCHEDULING,
            action=Action.SEARCH,
            topic=Topic.AVAILABILITY,
            confidence=0.99,
            conversation_marker=route.conversation_marker,
            source=RouteSource.CONTEXT,
            reason="continued reschedule date collection",
        )
    if (
        context.directory.doctor_ids
        and route.domain == Domain.DIRECTORY
        and route.topic == Topic.INSURER
        and any(term in text.split() for term in ("eles", "elas", "esses", "essas"))
    ):
        return RouteDecision(
            domain=Domain.DIRECTORY,
            action=Action.SEARCH,
            topic=Topic.DOCTOR,
            confidence=0.99,
            secondary_topics=[Topic.INSURER],
            conversation_marker=route.conversation_marker,
            source=RouteSource.CONTEXT,
            reason="continued directory result",
        )
    if route.domain != Domain.FALLBACK or context.active_topic != Topic.AVAILABILITY:
        return route
    if has_temporal_preference:
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
