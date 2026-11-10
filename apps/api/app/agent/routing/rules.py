from __future__ import annotations

import unicodedata
from collections.abc import Callable
from typing import Protocol

from app.agent.routing.models import Action, Domain, RiskLevel, RouteDecision, Topic


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(char if char.isalnum() else " " for char in without_accents).split())


def decision(
    domain: Domain, action: Action, topic: Topic, confidence: float = 0.98, **values
) -> RouteDecision:
    return RouteDecision(domain=domain, action=action, topic=topic, confidence=confidence, **values)


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
        text = normalize(message)
        if any(
            text == term or text.startswith(term + " ")
            for term in ("oi", "ola", "bom dia", "boa tarde", "boa noite")
        ):
            return decision(Domain.CONVERSATION, Action.GREET, Topic.GENERAL)
        if any(term in text for term in ("obrigado", "obrigada", "valeu")):
            return decision(Domain.CONVERSATION, Action.THANK, Topic.GENERAL)
        if any(term in text for term in ("tchau", "ate logo")):
            return decision(Domain.CONVERSATION, Action.FAREWELL, Topic.GENERAL)
        if any(term in text for term in ("o que voce faz", "como pode ajudar", "suas funcoes")):
            return decision(Domain.CONVERSATION, Action.DESCRIBE, Topic.GENERAL)
        return None


class PatientRule:
    def evaluate(self, message: str) -> RouteDecision | None:
        text = normalize(message)
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
        if any(
            term in text for term in ("agendar", "marcar", "horario", "disponibilidade", "agenda")
        ):
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
        if any(term in text for term in ("convenio", "plano de saude")):
            return decision(Domain.DIRECTORY, Action.LIST, Topic.INSURER)
        if "especialidad" in text:
            return decision(Domain.DIRECTORY, Action.LIST, Topic.SPECIALTY)
        if any(term in text for term in ("unidade", "endereco", "onde fica")):
            return decision(Domain.DIRECTORY, Action.LIST, Topic.UNIT)
        if any(
            term in text for term in ("medico", "doutor", "profissional", "cardiolog", "pediatr")
        ):
            return decision(Domain.DIRECTORY, Action.SEARCH, Topic.DOCTOR)
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

    def __init__(self, classifier=None):
        self.classifier = classifier

    def evaluate(self, message: str) -> RouteDecision | None:
        if self.classifier:
            return self.classifier(message)
        if normalize(message):
            return decision(
                Domain.FALLBACK,
                Action.CLARIFY,
                Topic.UNKNOWN,
                0.4,
                needs_clarification=True,
                reason="safe deterministic fallback",
            )
        return decision(
            Domain.FALLBACK,
            Action.CLARIFY,
            Topic.UNKNOWN,
            0.3,
            needs_clarification=True,
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
        for rule in self.rules:
            match = rule.evaluate(message)
            if match:
                return match
        return decision(
            Domain.FALLBACK, Action.CLARIFY, Topic.UNKNOWN, 0.3, needs_clarification=True
        )
