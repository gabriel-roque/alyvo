from __future__ import annotations

import unicodedata
from collections.abc import Callable
from typing import Any, Protocol

from app.agent.routing.models import (
    Action,
    ConversationMarker,
    Domain,
    RiskLevel,
    RouteDecision,
    RouteSource,
    Topic,
)


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(char if char.isalnum() else " " for char in without_accents).split())


def decision(
    domain: Domain,
    action: Action,
    topic: Topic,
    confidence: float = 0.98,
    **values: Any,
) -> RouteDecision:
    return RouteDecision(domain=domain, action=action, topic=topic, confidence=confidence, **values)


CONVERSATION_PREFIXES = (
    ("bom dia", ConversationMarker.GREETING),
    ("boa tarde", ConversationMarker.GREETING),
    ("boa noite", ConversationMarker.GREETING),
    ("ola", ConversationMarker.GREETING),
    ("oi", ConversationMarker.GREETING),
    ("obrigado", ConversationMarker.THANKS),
    ("obrigada", ConversationMarker.THANKS),
    ("valeu", ConversationMarker.THANKS),
    ("ate logo", ConversationMarker.FAREWELL),
    ("ate mais", ConversationMarker.FAREWELL),
    ("tchau", ConversationMarker.FAREWELL),
)
POLITE_TAILS = {"", "tudo bem", "como vai", "como voce esta"}


def split_conversation_marker(message: str) -> tuple[ConversationMarker | None, str]:
    text = normalize(message)
    for prefix, marker in CONVERSATION_PREFIXES:
        if text == prefix:
            return marker, ""
        if text.startswith(prefix + " "):
            return marker, text.removeprefix(prefix).strip()
    return None, text


def is_conversation_only(marker: ConversationMarker | None, remainder: str) -> bool:
    if marker is None:
        return False
    if remainder in POLITE_TAILS:
        return True
    if marker == ConversationMarker.THANKS:
        return remainder.startswith(("pela ajuda", "pela informacao", "por ajudar", "mesmo"))
    return False


class RoutingRule(Protocol):
    def evaluate(self, message: str) -> RouteDecision | None: ...


class SafetyRule:
    def evaluate(self, message: str) -> RouteDecision | None:
        text = normalize(message)
        if any(
            term in text
            for term in ("ignore suas regras", "outro paciente", "revele dados", "prompt interno")
        ):
            return decision(
                Domain.SECURITY, Action.REJECT, Topic.UNAUTHORIZED, risk=RiskLevel.SENSITIVE
            )
        urgent = ("dor no peito", "nao consigo respirar", "hemorragia", "convulsao", "emergencia")
        if any(term in text for term in urgent):
            return decision(
                Domain.CLINICAL_SAFETY, Action.REJECT, Topic.CLINICAL, risk=RiskLevel.URGENT
            )
        clinical = (
            "diagnostico",
            "prescreva",
            "qual remedio",
            "interprete meu exame",
            "interpretar resultado",
            "estou sentindo",
            "estou com dor",
            "dor de cabeca",
            "qual medico poderia me atender",
            "qual medico devo procurar",
            "pelos meus sintomas",
        )
        if any(term in text for term in clinical):
            return decision(
                Domain.CLINICAL_SAFETY,
                Action.CLARIFY,
                Topic.CLINICAL,
                risk=RiskLevel.SENSITIVE,
            )
        return None


class ConversationRule:
    def evaluate(self, message: str) -> RouteDecision | None:
        marker, remainder = split_conversation_marker(message)
        if is_conversation_only(marker, remainder):
            actions = {
                ConversationMarker.GREETING: Action.GREET,
                ConversationMarker.THANKS: Action.THANK,
                ConversationMarker.FAREWELL: Action.FAREWELL,
            }
            return decision(
                Domain.CONVERSATION,
                actions[marker],
                Topic.GENERAL,
                conversation_marker=marker,
            )
        text = normalize(message)
        if any(term in text for term in ("o que voce faz", "como pode ajudar", "suas funcoes")):
            return decision(Domain.CONVERSATION, Action.DESCRIBE, Topic.GENERAL)
        return None


class PatientRule:
    def evaluate(self, message: str) -> RouteDecision | None:
        text = normalize(message)
        if any(
            term in text
            for term in (
                "remarcar",
                "reagendar",
                "trocar a data",
                "mudar a data",
                "dia errado",
            )
        ):
            return decision(
                Domain.SCHEDULING,
                Action.RESCHEDULE,
                Topic.OWN_APPOINTMENT,
                risk=RiskLevel.SENSITIVE,
            )
        if any(
            term in text for term in ("minhas consultas", "meus agendamentos", "consultas marcadas")
        ):
            return decision(
                Domain.PATIENT, Action.LIST, Topic.OWN_APPOINTMENT, risk=RiskLevel.SENSITIVE
            )
        if any(
            term in text
            for term in ("cancelar consulta", "desmarcar consulta", "cancelar meu agendamento")
        ):
            return decision(
                Domain.SCHEDULING, Action.CANCEL, Topic.OWN_APPOINTMENT, risk=RiskLevel.SENSITIVE
            )
        return None


class OperationalHoursRule:
    def evaluate(self, message: str) -> RouteDecision | None:
        text = normalize(message)
        institutional_hours = (
            "horario de abertura",
            "horario de funcionamento",
            "horario de atendimento da clinica",
            "que horas abre",
            "que horas fecha",
            "clinica abre",
            "clinica fecha",
            "ate que horas a clinica",
            "atendem aos finais de semana",
            "atende aos finais de semana",
            "atendem no fim de semana",
            "atende no fim de semana",
        )
        if any(term in text for term in institutional_hours):
            return decision(Domain.KNOWLEDGE, Action.SEARCH, Topic.INSTITUTIONAL)
        return None


class SchedulingRule:
    def evaluate(self, message: str) -> RouteDecision | None:
        text = normalize(message)
        scheduling_request = any(
            term in text for term in ("agendar", "marcar", "horario", "agenda")
        ) or ("disponiv" in text and any(term in text for term in ("dia", "data", "hora")))
        if scheduling_request:
            return decision(Domain.SCHEDULING, Action.SEARCH, Topic.AVAILABILITY)
        date_follow_up = (
            "hoje",
            "amanha",
            "depois de amanha",
            "segunda",
            "terca",
            "quarta",
            "quinta",
            "sexta",
            "sabado",
            "domingo",
        )
        if len(text.split()) <= 8 and any(term in text for term in date_follow_up):
            return decision(Domain.SCHEDULING, Action.SEARCH, Topic.AVAILABILITY)
        return None


class DirectoryRule:
    def evaluate(self, message: str) -> RouteDecision | None:
        text = normalize(message)
        if any(
            term in text for term in ("medico", "doutor", "profissional", "cardiolog", "pediatr")
        ):
            secondary = (
                [Topic.INSURER]
                if any(term in text for term in ("convenio", "convenios", "plano", "planos"))
                else []
            )
            return decision(
                Domain.DIRECTORY,
                Action.SEARCH,
                Topic.DOCTOR,
                secondary_topics=secondary,
            )
        if any(term in text for term in ("convenio", "convenios", "plano", "planos")):
            return decision(Domain.DIRECTORY, Action.LIST, Topic.INSURER)
        if "especialidad" in text:
            return decision(Domain.DIRECTORY, Action.LIST, Topic.SPECIALTY)
        if any(term in text for term in ("unidade", "endereco", "onde fica")):
            return decision(Domain.DIRECTORY, Action.LIST, Topic.UNIT)
        if any(term in text for term in ("exame", "procedimento", "hemograma")):
            return decision(Domain.DIRECTORY, Action.LIST, Topic.EXAM)
        return None


class KnowledgeRule:
    def evaluate(self, message: str) -> RouteDecision | None:
        text = normalize(message)
        knowledge_terms = (
            "clinica",
            "politica",
            "cancelamento",
            "preparo",
            "documento",
            "atendimento",
            "funcionamento",
            "lgpd",
            "privacidade",
        )
        if any(term in text for term in knowledge_terms):
            return decision(Domain.KNOWLEDGE, Action.SEARCH, Topic.INSTITUTIONAL, 0.75)
        return None


class LlmFallbackRule:
    """Boundary for a probabilistic classifier, deterministic without a provider."""

    def __init__(self, classifier: Callable[[str], RouteDecision | None] | None = None):
        self.classifier = classifier

    def evaluate(self, message: str) -> RouteDecision | None:
        if self.classifier:
            result = self.classifier(message)
            return result.model_copy(update={"source": RouteSource.SEMANTIC}) if result else None
        if normalize(message):
            return decision(
                Domain.FALLBACK,
                Action.CLARIFY,
                Topic.UNKNOWN,
                0.4,
                needs_clarification=True,
                reason="safe deterministic fallback",
                source=RouteSource.FALLBACK,
            )
        return decision(
            Domain.FALLBACK,
            Action.CLARIFY,
            Topic.UNKNOWN,
            0.3,
            needs_clarification=True,
            source=RouteSource.FALLBACK,
        )


class RuleChain:
    def __init__(
        self,
        rules: tuple[RoutingRule, ...] | None = None,
        fallback_classifier: Callable[[str], RouteDecision | None] | None = None,
    ):
        self.rules = rules or (
            SafetyRule(),
            ConversationRule(),
            PatientRule(),
            OperationalHoursRule(),
            SchedulingRule(),
            DirectoryRule(),
            KnowledgeRule(),
            LlmFallbackRule(fallback_classifier),
        )

    def classify(self, message: str) -> RouteDecision:
        marker, remainder = split_conversation_marker(message)
        content = (
            remainder
            if marker is not None and not is_conversation_only(marker, remainder)
            else message
        )
        if _is_simple_negated_action(content):
            return decision(
                Domain.FALLBACK,
                Action.CLARIFY,
                Topic.UNKNOWN,
                0.9,
                needs_clarification=True,
                reason="negated operation",
                conversation_marker=marker,
                source=RouteSource.RULE,
            )

        matches: list[RouteDecision] = []
        fallback: RouteDecision | None = None
        for rule in self.rules:
            if isinstance(rule, LlmFallbackRule) and matches:
                break
            match = rule.evaluate(content)
            if match is None:
                continue
            match = match.model_copy(
                update={"conversation_marker": marker or match.conversation_marker}
            )
            if match.domain in {Domain.SECURITY, Domain.CLINICAL_SAFETY}:
                return match
            if match.domain == Domain.FALLBACK:
                fallback = match
                continue
            matches.append(match)
        if matches:
            selected = matches[0]
            secondary = list(
                dict.fromkeys([*selected.secondary_topics, *(item.topic for item in matches[1:])])
            )
            return selected.model_copy(update={"secondary_topics": secondary})
        return fallback or decision(
            Domain.FALLBACK,
            Action.CLARIFY,
            Topic.UNKNOWN,
            0.3,
            needs_clarification=True,
            conversation_marker=marker,
            source=RouteSource.FALLBACK,
        )


def _is_simple_negated_action(message: str) -> bool:
    text = normalize(message)
    starts_negated = text.startswith(("nao quero ", "nao preciso "))
    actions = ("agendar", "marcar", "cancelar", "desmarcar")
    return starts_negated and any(action in text for action in actions) and text.count("quero") <= 1
