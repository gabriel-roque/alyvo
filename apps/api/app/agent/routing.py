from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ai.conversation import normalized_text, resolve_date_window


class Domain(StrEnum):
    CONVERSATION = "conversation"
    KNOWLEDGE = "knowledge"
    INSTITUTIONAL = "institutional"  # v1 compatibility; normalized to knowledge
    DIRECTORY = "directory"
    SCHEDULING = "scheduling"
    EXAMS = "exams"
    PATIENT = "patient_administration"
    FINANCIAL = "financial"
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
    INTERPRET = "interpret"
    HANDOFF = "handoff"
    CLARIFY = "clarify"
    REJECT = "reject"


class Topic(StrEnum):
    RETURN_POLICY = "return_policy"
    EXAM_CATALOG = "exam_catalog"
    EXAM_RELEASE_TIME = "exam_release_time"
    EXAM_PREPARATION = "exam_preparation"
    OPENING_HOURS = "opening_hours"
    INSTITUTIONAL_POLICY = "institutional_policy"
    UNIT_LOCATION = "unit_location"
    DOCTOR = "doctor"
    SPECIALTY = "specialty"
    INSURER = "insurer"
    AVAILABILITY = "availability"
    OWN_APPOINTMENT = "own_appointment"
    PRIVACY_OR_RECORD = "privacy_or_record"
    FINANCIAL = "financial"
    CLINICAL_GUIDANCE = "clinical_guidance"
    POSSIBLE_EMERGENCY = "possible_emergency"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    GENERAL = "general"
    UNKNOWN = "unknown"


class RiskLevel(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    URGENT = "urgent"


LEGACY_INTENTS: dict[tuple[Domain, Action, Topic], str] = {
    (Domain.CONVERSATION, Action.GREET, Topic.GENERAL): "greeting",
    (Domain.CONVERSATION, Action.THANK, Topic.GENERAL): "thanks",
    (Domain.CONVERSATION, Action.FAREWELL, Topic.GENERAL): "farewell",
    (Domain.CONVERSATION, Action.DESCRIBE, Topic.GENERAL): "capabilities",
    (Domain.DIRECTORY, Action.LIST, Topic.INSURER): "list_insurers",
    (Domain.DIRECTORY, Action.LIST, Topic.SPECIALTY): "list_specialties",
    (Domain.DIRECTORY, Action.LIST, Topic.DOCTOR): "list_doctors",
    (Domain.DIRECTORY, Action.SEARCH, Topic.DOCTOR): "list_doctors",
    (Domain.DIRECTORY, Action.LIST, Topic.UNIT_LOCATION): "list_units",
    (Domain.DIRECTORY, Action.SEARCH, Topic.UNIT_LOCATION): "unit_location",
    (Domain.SCHEDULING, Action.SEARCH, Topic.AVAILABILITY): "search_availability",
    (Domain.SCHEDULING, Action.CANCEL, Topic.OWN_APPOINTMENT): "cancel_appointment",
    (Domain.SCHEDULING, Action.RESCHEDULE, Topic.OWN_APPOINTMENT): "reschedule_appointment",
    (Domain.PATIENT, Action.LIST, Topic.OWN_APPOINTMENT): "list_my_appointments",
    (Domain.EXAMS, Action.LIST, Topic.EXAM_CATALOG): "list_exams",
    (Domain.EXAMS, Action.SEARCH, Topic.EXAM_PREPARATION): "exam_preparation",
    (Domain.EXAMS, Action.SEARCH, Topic.EXAM_RELEASE_TIME): "search_knowledge",
    (Domain.KNOWLEDGE, Action.SEARCH, Topic.RETURN_POLICY): "search_knowledge",
    (Domain.KNOWLEDGE, Action.SEARCH, Topic.OPENING_HOURS): "opening_hours",
    (Domain.KNOWLEDGE, Action.SEARCH, Topic.INSTITUTIONAL_POLICY): "institutional_knowledge",
    (Domain.CLINICAL_SAFETY, Action.REJECT, Topic.POSSIBLE_EMERGENCY): "possible_emergency",
    (Domain.CLINICAL_SAFETY, Action.REJECT, Topic.CLINICAL_GUIDANCE): "clinical_guidance_request",
    (Domain.SECURITY, Action.REJECT, Topic.UNAUTHORIZED_ACCESS): "unauthorized_or_injection",
}


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    domain: Domain
    action: Action
    topic: Topic
    risk_level: RiskLevel = RiskLevel.NORMAL
    entities: dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool = False
    unsupported_reason: str | None = None

    @field_validator("unsupported_reason", mode="before")
    @classmethod
    def normalize_nullable_strings(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().casefold() in {"", "none", "null", "n/a"}:
            return None
        return value

    @property
    def intent(self) -> str:
        if self.needs_clarification:
            return "ambiguous_request"
        return LEGACY_INTENTS.get(
            (self.domain, self.action, self.topic),
            self.topic.value if self.topic != Topic.UNKNOWN else "unsupported",
        )


CAPABILITY_TERMS = (
    "o que voce faz",
    "como voce pode ajudar",
    "no que pode me ajudar",
    "no que voce pode me ajudar",
    "quais coisas voce faz",
    "suas funcoes",
)


def _route(
    domain: Domain,
    action: Action,
    topic: Topic,
    confidence: float = 1.0,
    **values: Any,
) -> RouteDecision:
    return RouteDecision(
        domain=domain,
        action=action,
        topic=topic,
        confidence=confidence,
        **values,
    )


def deterministic_classification(message: str) -> RouteDecision | None:
    """Route only high-confidence, safety-critical or operational requests.

    Broad administrative questions deliberately fall through to structured model
    routing; known semantic families are explicit so wording changes do not alter
    the route.
    """

    text = normalized_text(message)
    tokens = set(text.split())
    if not text:
        return _route(
            Domain.FALLBACK,
            Action.CLARIFY,
            Topic.UNKNOWN,
            needs_clarification=True,
        )

    if any(
        term in text
        for term in (
            "ignore suas regras",
            "revele dados",
            "outro paciente",
            "prompt",
            "segredo interno",
        )
    ):
        return _route(
            Domain.SECURITY,
            Action.REJECT,
            Topic.UNAUTHORIZED_ACCESS,
            risk_level=RiskLevel.SENSITIVE,
        )

    if any(
        term in text
        for term in (
            "dor no peito",
            "nao consigo respirar",
            "desmaio",
            "hemorragia",
            "sangramento intenso",
            "convulsao",
            "emergencia",
        )
    ):
        return _route(
            Domain.CLINICAL_SAFETY,
            Action.REJECT,
            Topic.POSSIBLE_EMERGENCY,
            risk_level=RiskLevel.URGENT,
        )

    interpretation = any(
        term in text
        for term in (
            "diagnostico",
            "qual doenca",
            "prescreva",
            "prescricao",
            "receita medica",
            "qual remedio",
            "dose do remedio",
            "trocar medicamento",
            "interprete meu exame",
            "interpretar resultado",
            "o que significa meu resultado",
        )
    ) or (
        bool(tokens & {"interprete", "interpretar"})
        and bool(tokens & {"exame", "resultado", "laudo"})
    )
    if interpretation:
        return _route(
            Domain.CLINICAL_SAFETY,
            Action.REJECT,
            Topic.CLINICAL_GUIDANCE,
            risk_level=RiskLevel.SENSITIVE,
        )

    greetings = ("oi", "ola", "bom dia", "boa tarde", "boa noite", "e ai")
    if any(text == item or text.startswith(f"{item} ") for item in greetings):
        return _route(Domain.CONVERSATION, Action.GREET, Topic.GENERAL)
    if any(term in text for term in ("obrigado", "obrigada", "valeu", "agradeco")):
        return _route(Domain.CONVERSATION, Action.THANK, Topic.GENERAL)
    if any(term in text for term in ("tchau", "ate logo", "encerrar conversa")):
        return _route(Domain.CONVERSATION, Action.FAREWELL, Topic.GENERAL)
    if any(term in text for term in CAPABILITY_TERMS):
        return _route(Domain.CONVERSATION, Action.DESCRIBE, Topic.GENERAL)
    if any(term in text for term in ("atendente", "falar com uma pessoa", "atendimento humano")):
        return _route(
            Domain.CONVERSATION,
            Action.HANDOFF,
            Topic.GENERAL,
            unsupported_reason="O canal de atendimento humano ainda não está integrado.",
        )

    # Semantic family: return policy. This must precede generic scheduling.
    return_subject = bool(tokens & {"retorno", "voltar"}) and bool(
        tokens & {"consulta", "consultas", "atendimento", "particular", "convenio"}
    )
    return_question = bool(
        tokens & {"prazo", "prazos", "limite", "politica", "dias", "quando", "depois"}
    )
    if return_subject and return_question:
        return _route(Domain.KNOWLEDGE, Action.SEARCH, Topic.RETURN_POLICY, 0.99)

    # Semantic family: exam result release time, distinct from interpretation.
    exam_context = any(
        term in text for term in ("exame", "exames", "hemograma", "sangue", "resultado", "laudo")
    )
    release_context = any(
        term in text
        for term in (
            "prazo",
            "prazos",
            "quando fica pronto",
            "quando sai",
            "tempo para ficar pronto",
            "liberacao",
            "liberado",
            "resultado pronto",
            "data limite",
        )
    ) or ("pronto" in tokens and bool(tokens & {"quando", "tempo", "resultado", "laudo"}))
    if exam_context and release_context:
        return _route(Domain.EXAMS, Action.SEARCH, Topic.EXAM_RELEASE_TIME, 0.99)

    if any(
        term in text
        for term in (
            "prontuario",
            "excluir meus dados",
            "corrigir meus dados",
            "lgpd",
            "privacidade",
        )
    ):
        return _route(
            Domain.PATIENT,
            Action.REJECT,
            Topic.PRIVACY_OR_RECORD,
            0.98,
            risk_level=RiskLevel.SENSITIVE,
            unsupported_reason="Esta solicitação exige atendimento autenticado da clínica.",
        )
    if any(
        term in text
        for term in (
            "preco",
            "valor",
            "quanto custa",
            "coparticipacao",
            "pagamento",
            "reembolso",
            "cobranca",
            "segunda via",
        )
    ):
        return _route(
            Domain.FINANCIAL,
            Action.REJECT,
            Topic.FINANCIAL,
            0.98,
            unsupported_reason="O Alyvo não possui integração financeira para confirmar valores ou cobertura.",
        )
    if any(term in text for term in ("reagendar", "remarcar")):
        return _route(
            Domain.SCHEDULING,
            Action.RESCHEDULE,
            Topic.OWN_APPOINTMENT,
            unsupported_reason="O reagendamento automático ainda não está disponível.",
        )
    if any(
        term in text for term in ("minhas consultas", "meus agendamentos", "consultas marcadas")
    ):
        return _route(
            Domain.PATIENT,
            Action.LIST,
            Topic.OWN_APPOINTMENT,
            risk_level=RiskLevel.SENSITIVE,
        )
    if any(
        term in text
        for term in (
            "cancelar consulta",
            "cancelar uma consulta",
            "desmarcar consulta",
            "desmarcar uma consulta",
            "cancelar meu agendamento",
        )
    ):
        return _route(
            Domain.SCHEDULING,
            Action.CANCEL,
            Topic.OWN_APPOINTMENT,
            risk_level=RiskLevel.SENSITIVE,
        )

    if any(
        term in text for term in ("abre", "fecha", "funcionamento", "fuso", "sao paulo", "timezone")
    ):
        return _route(Domain.KNOWLEDGE, Action.SEARCH, Topic.OPENING_HOURS, 0.98)

    scheduling = any(
        term in text
        for term in (
            "agendar",
            "marcar",
            "marca consulta",
            "horario",
            "orario",
            "disponibilidade",
            "agenda",
        )
    ) or (
        resolve_date_window(message) is not None
        and bool(tokens & {"consulta", "medico", "doutor", "pediatra", "cardiologista"})
    )
    if scheduling:
        return _route(Domain.SCHEDULING, Action.SEARCH, Topic.AVAILABILITY, 0.98)

    insurer_context = any(
        term in text
        for term in (
            "convenio",
            "convenios",
            "plano de saude",
            "planos de saude",
            "plano aceito",
            "planos aceitos",
        )
    )
    if insurer_context:
        doctor_context = any(
            term in text
            for term in (
                "medico",
                "doutor",
                "dr ",
                "dra",
                "profissional",
                "profissionais",
                "profisional",
                "profisionais",
                "cardiolog",
                "pediatr",
            )
        )
        return _route(
            Domain.DIRECTORY,
            Action.SEARCH if doctor_context else Action.LIST,
            Topic.DOCTOR if doctor_context else Topic.INSURER,
            0.98,
        )

    exam_context = any(
        term in text for term in ("exame", "exames", "procedimento", "procedimentos", "hemograma")
    )
    if exam_context:
        if any(
            term in text
            for term in (
                "preparo",
                "jejum",
                "documento",
                "carteirinha",
                "pedido medico",
                "recepcao",
                "exigencia",
                "antes do exame",
            )
        ):
            return _route(Domain.EXAMS, Action.SEARCH, Topic.EXAM_PREPARATION, 0.98)
        return _route(Domain.EXAMS, Action.LIST, Topic.EXAM_CATALOG, 0.98)

    if any(
        term in text
        for term in (
            "jejum",
            "preparo",
            "preparacao",
            "documento",
            "carteirinha",
            "pedido medico",
            "recepcao",
            "quanto dura",
            "duracao",
        )
    ):
        return _route(Domain.KNOWLEDGE, Action.SEARCH, Topic.INSTITUTIONAL_POLICY, 0.95)
    if any(term in text for term in ("especialidade", "especialidades")):
        return _route(Domain.DIRECTORY, Action.LIST, Topic.SPECIALTY, 0.98)
    if any(term in text for term in ("unidades", "quais unidades")):
        return _route(Domain.DIRECTORY, Action.LIST, Topic.UNIT_LOCATION, 0.98)
    if any(term in text for term in ("onde fica", "onde e", "endereco", "localizacao")):
        return _route(Domain.DIRECTORY, Action.SEARCH, Topic.UNIT_LOCATION, 0.98)
    if any(
        term in text
        for term in (
            "medico",
            "medicos",
            "doutor",
            "dr ",
            "dra",
            "profissional",
            "profissionais",
            "profisional",
            "profisionais",
            "cardiolog",
            "cardeolog",
            "pediatr",
        )
    ):
        return _route(Domain.DIRECTORY, Action.SEARCH, Topic.DOCTOR, 0.95)
    if any(
        term in text
        for term in (
            "abre",
            "fecha",
            "funcionamento",
            "feriado",
            "fim de semana",
            "fuso",
            "timezone",
        )
    ):
        return _route(Domain.KNOWLEDGE, Action.SEARCH, Topic.OPENING_HOURS, 0.95)
    if any(
        term in text
        for term in (
            "estacionamento",
            "acessibilidade",
            "acompanhante",
            "visita",
            "cafeteria",
            "alimentacao",
            "politica",
            "orientacao",
            "instrucao",
        )
    ):
        return _route(Domain.KNOWLEDGE, Action.SEARCH, Topic.INSTITUTIONAL_POLICY, 0.9)
    return None


# Temporary source compatibility for integrations importing the old name.
IntentClassification = RouteDecision
