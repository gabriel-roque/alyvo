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
    "semana que vem",
    "fim do mes",
    "final do mes",
    "dia ",
    " de janeiro",
    " de fevereiro",
    " de marco",
    " de abril",
    " de maio",
    " de junho",
    " de julho",
    " de agosto",
    " de setembro",
    " de outubro",
    " de novembro",
    " de dezembro",
)

AFFIRMATIVES = {
    "sim",
    "isso",
    "exato",
    "exatamente",
    "correto",
    "pode ser",
    "confirmo",
}

NEGATIVES = {"nao", "negativo", "deixa", "deixa pra la", "agora nao"}

DIRECTORY_REFERENCES = {"ele", "ela", "eles", "elas", "esse", "essa", "esses", "essas"}


def resolve_from_context(
    route: RouteDecision, message: str, context: ConversationContext
) -> RouteDecision:
    if route.domain in {Domain.SECURITY, Domain.CLINICAL_SAFETY}:
        return route
    text = normalize(message)
    temporal = _has_temporal_preference(message, text)
    candidates = (
        _presented_slot_route(route, text, context),
        _pending_answer_route(route, text, context),
        _reschedule_route(route, context, temporal),
        _directory_reference_route(route, text, context),
        _availability_continuation_route(route, context, temporal),
    )
    for candidate in candidates:
        if candidate is not None:
            return candidate
    return route


def _presented_slot_route(
    route: RouteDecision, text: str, context: ConversationContext
) -> RouteDecision | None:
    if not context.presented_availability.slots or not _references_presented_slot(text):
        return None
    return _context_route(
        route,
        Domain.SCHEDULING,
        Action.CREATE,
        Topic.AVAILABILITY,
        "selected presented availability slot",
    )


def _pending_answer_route(
    route: RouteDecision, text: str, context: ConversationContext
) -> RouteDecision | None:
    pending = context.pending_question
    if pending is not None and pending.kind == "directory_follow_up" and text in AFFIRMATIVES:
        return _context_route(
            route,
            Domain.DIRECTORY,
            Action.SEARCH,
            Topic.DOCTOR,
            "confirmed directory follow-up",
        )
    if pending is not None and text in NEGATIVES:
        return _context_route(
            route,
            Domain.CONVERSATION,
            Action.DESCRIBE,
            Topic.GENERAL,
            "declined pending question",
        )
    return None


def _reschedule_route(
    route: RouteDecision, context: ConversationContext, temporal: bool
) -> RouteDecision | None:
    if context.pending_reschedule is None or not temporal:
        return None
    return _context_route(
        route,
        Domain.SCHEDULING,
        Action.SEARCH,
        Topic.AVAILABILITY,
        "continued reschedule date collection",
    )


def _directory_reference_route(
    route: RouteDecision, text: str, context: ConversationContext
) -> RouteDecision | None:
    matches = (
        context.directory.doctor_ids
        and route.domain == Domain.DIRECTORY
        and route.topic == Topic.INSURER
        and any(term in text.split() for term in DIRECTORY_REFERENCES)
    )
    if not matches:
        return None
    return _context_route(
        route,
        Domain.DIRECTORY,
        Action.SEARCH,
        Topic.DOCTOR,
        "continued directory result",
        secondary_topics=[Topic.INSURER],
    )


def _availability_continuation_route(
    route: RouteDecision, context: ConversationContext, temporal: bool
) -> RouteDecision | None:
    if (
        route.domain != Domain.FALLBACK
        or context.active_topic != Topic.AVAILABILITY
        or not temporal
    ):
        return None
    return _context_route(
        route,
        Domain.SCHEDULING,
        Action.SEARCH,
        Topic.AVAILABILITY,
        "continued availability collection",
    )


def _context_route(
    route: RouteDecision,
    domain: Domain,
    action: Action,
    topic: Topic,
    reason: str,
    secondary_topics: list[Topic] | None = None,
) -> RouteDecision:
    return RouteDecision(
        domain=domain,
        action=action,
        topic=topic,
        confidence=0.99,
        secondary_topics=secondary_topics or [],
        conversation_marker=route.conversation_marker,
        source=RouteSource.CONTEXT,
        reason=reason,
    )


def _has_temporal_preference(message: str, text: str) -> bool:
    has_date = bool(re.search(r"\b(?:20\d{2}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2})\b", message))
    return has_date or any(term in text for term in TEMPORAL_TERMS)


def _references_presented_slot(text: str) -> bool:
    ordinal = any(
        term in text
        for term in (
            "primeiro",
            "primeira",
            "segundo",
            "segunda opcao",
            "terceiro",
            "terceira",
            "ultimo",
            "ultima",
        )
    )
    clock = bool(re.search(r"\b(?:as|a)\s+\d{1,2}(?::\d{2})?\b", text))
    numbered = bool(re.search(r"\bopcao\s+\d{1,2}\b", text))
    return ordinal or clock or numbered
