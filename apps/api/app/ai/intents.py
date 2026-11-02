from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.ai.conversation import normalized_text, resolve_date_window


class Domain(StrEnum):
    CONVERSATION = "conversation"
    INSTITUTIONAL = "institutional"
    DIRECTORY = "directory"
    SCHEDULING = "scheduling"
    EXAMS = "exams"
    PATIENT = "patient_administration"
    FINANCIAL = "financial"
    KNOWLEDGE = "knowledge"
    CLINICAL_SAFETY = "clinical_safety"
    SECURITY = "security"
    FALLBACK = "fallback"


class RiskLevel(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    URGENT = "urgent"


class IntentClassification(BaseModel):
    domain: Domain
    intent: str
    action: str | None = None
    entities: dict[str, str] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.NORMAL
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool = False
    unsupported_reason: str | None = None


CAPABILITY_TERMS = (
    "o que voce faz",
    "como voce pode ajudar",
    "no que pode me ajudar",
    "no que voce pode me ajudar",
    "quais coisas voce faz",
    "suas funcoes",
)


def deterministic_classification(message: str) -> IntentClassification | None:
    """Classify high-confidence and safety-sensitive requests without an LLM.

    The taxonomy intentionally recognizes more requests than the product can
    execute. Unsupported operations are explicit instead of being routed to RAG.
    """

    text = normalized_text(message)
    tokens = set(text.split())
    if not text:
        return IntentClassification(
            domain=Domain.FALLBACK,
            intent="empty_message",
            confidence=1,
            needs_clarification=True,
        )

    if any(term in text for term in ("ignore suas regras", "revele dados", "outro paciente", "prompt", "segredo interno")):
        return IntentClassification(
            domain=Domain.SECURITY,
            intent="unauthorized_or_injection",
            risk_level=RiskLevel.SENSITIVE,
            confidence=1,
        )

    urgent = any(term in text for term in (
        "dor no peito", "nao consigo respirar", "nao consigo respirar", "desmaio",
        "hemorragia", "sangramento intenso", "convulsao", "emergencia",
    ))
    if urgent:
        return IntentClassification(
            domain=Domain.CLINICAL_SAFETY,
            intent="possible_emergency",
            risk_level=RiskLevel.URGENT,
            confidence=1,
        )
    if any(term in text for term in (
        "diagnostico", "qual doenca", "prescreva", "prescricao", "receita medica",
        "qual remedio", "dose do remedio", "trocar medicamento", "interprete meu exame",
        "interpretar resultado", "o que significa meu resultado",
    )):
        return IntentClassification(
            domain=Domain.CLINICAL_SAFETY,
            intent="clinical_guidance_request",
            risk_level=RiskLevel.SENSITIVE,
            confidence=1,
        )

    greetings = ("oi", "ola", "bom dia", "boa tarde", "boa noite", "e ai")
    if any(text == item or text.startswith(f"{item} ") for item in greetings):
        return IntentClassification(domain=Domain.CONVERSATION, intent="greeting", confidence=1)
    if any(term in text for term in ("obrigado", "obrigada", "valeu", "agradeco")):
        return IntentClassification(domain=Domain.CONVERSATION, intent="thanks", confidence=1)
    if any(term in text for term in ("tchau", "ate logo", "encerrar conversa")):
        return IntentClassification(domain=Domain.CONVERSATION, intent="farewell", confidence=1)
    if any(term in text for term in CAPABILITY_TERMS):
        return IntentClassification(domain=Domain.CONVERSATION, intent="capabilities", confidence=1)
    if any(term in text for term in ("atendente", "falar com uma pessoa", "atendimento humano")):
        return IntentClassification(
            domain=Domain.CONVERSATION,
            intent="human_handoff",
            confidence=1,
            unsupported_reason="O canal de atendimento humano ainda não está integrado.",
        )

    if any(term in text for term in ("prontuario", "excluir meus dados", "corrigir meus dados", "lgpd", "privacidade")):
        return IntentClassification(
            domain=Domain.PATIENT,
            intent="privacy_or_record_request",
            risk_level=RiskLevel.SENSITIVE,
            confidence=0.98,
            unsupported_reason="Esta solicitação exige atendimento autenticado da clínica.",
        )

    if any(term in text for term in ("preco", "valor", "quanto custa", "coparticipacao", "pagamento", "reembolso", "cobranca", "segunda via")):
        return IntentClassification(
            domain=Domain.FINANCIAL,
            intent="financial_information",
            confidence=0.98,
            unsupported_reason="O Alyvo não possui integração financeira para confirmar valores ou cobertura.",
        )

    if any(term in text for term in ("reagendar", "remarcar")):
        return IntentClassification(
            domain=Domain.SCHEDULING,
            intent="reschedule_appointment",
            action="reschedule",
            confidence=1,
            unsupported_reason="O reagendamento automático ainda não está disponível.",
        )
    if any(term in text for term in ("minhas consultas", "meus agendamentos", "consultas marcadas")):
        return IntentClassification(
            domain=Domain.PATIENT,
            intent="list_my_appointments",
            action="list",
            risk_level=RiskLevel.SENSITIVE,
            confidence=1,
        )
    if any(term in text for term in (
        "cancelar consulta", "cancelar uma consulta", "desmarcar consulta",
        "desmarcar uma consulta", "cancelar meu agendamento",
    )):
        return IntentClassification(
            domain=Domain.SCHEDULING,
            intent="cancel_appointment",
            action="cancel",
            risk_level=RiskLevel.SENSITIVE,
            confidence=1,
        )

    if any(term in text for term in ("abre", "fecha", "funcionamento", "atendimento comeca", "fuso", "sao paulo", "timezone")):
        return IntentClassification(domain=Domain.INSTITUTIONAL, intent="opening_hours", confidence=0.98)

    scheduling = any(term in text for term in (
        "agendar", "marcar", "marca consulta", "horario", "orario",
        "disponibilidade", "agenda",
    )) or (resolve_date_window(message) is not None and bool(tokens & {"consulta", "medico", "doutor", "pediatra", "cardiologista"}))
    if scheduling:
        return IntentClassification(
            domain=Domain.SCHEDULING,
            intent="search_availability",
            action="search",
            confidence=0.98,
        )

    insurer_terms = ("convenio", "convenios", "plano de saude", "planos de saude", "plano aceito", "planos aceitos")
    if any(term in text for term in insurer_terms):
        doctor_context = any(term in text for term in (
            "medico", "doutor", "dr ", "dra", "profissional", "profissionais",
            "profisional", "profisionais",
            "cardiolog", "pediatr",
        ))
        return IntentClassification(
            domain=Domain.DIRECTORY,
            intent="search_doctors_by_insurer" if doctor_context else "list_insurers",
            action="search" if doctor_context else "list",
            confidence=0.98,
        )

    exam_terms = ("exame", "exames", "procedimento", "procedimentos")
    if any(term in text for term in exam_terms):
        if any(term in text for term in (
            "preparo", "jejum", "documento", "carteirinha", "pedido medico",
            "recepcao", "exigencia", "antes do exame",
        )):
            return IntentClassification(domain=Domain.EXAMS, intent="exam_preparation", confidence=0.98)
        if any(term in text for term in ("resultado", "interpret")):
            return IntentClassification(
                domain=Domain.CLINICAL_SAFETY,
                intent="exam_result_interpretation",
                risk_level=RiskLevel.SENSITIVE,
                confidence=1,
            )
        return IntentClassification(domain=Domain.EXAMS, intent="list_exams", action="list", confidence=0.98)

    if any(term in text for term in (
        "jejum", "preparo", "preparacao", "documento", "carteirinha",
        "pedido medico", "recepcao", "quanto dura", "duracao",
    )):
        return IntentClassification(
            domain=Domain.KNOWLEDGE,
            intent="institutional_knowledge",
            confidence=0.95,
        )

    if any(term in text for term in ("especialidade", "especialidades")):
        return IntentClassification(domain=Domain.DIRECTORY, intent="list_specialties", action="list", confidence=0.98)
    if any(term in text for term in ("unidades", "quais unidades")):
        return IntentClassification(domain=Domain.DIRECTORY, intent="list_units", action="list", confidence=0.98)
    if any(term in text for term in ("onde fica", "onde e", "endereco", "localizacao")):
        return IntentClassification(domain=Domain.INSTITUTIONAL, intent="unit_location", confidence=0.98)
    if any(term in text for term in (
        "medico", "medicos", "doutor", "dr ", "dra", "profissional", "profissionais",
        "profisional", "profisionais",
        "cardiolog", "cardeolog", "pediatr",
    )):
        return IntentClassification(domain=Domain.DIRECTORY, intent="list_doctors", action="search", confidence=0.95)

    if any(term in text for term in ("feriado", "fim de semana")):
        return IntentClassification(domain=Domain.INSTITUTIONAL, intent="opening_hours", confidence=0.95)
    if any(term in text for term in ("estacionamento", "acessibilidade", "acompanhante", "visita")):
        return IntentClassification(domain=Domain.KNOWLEDGE, intent="institutional_policy", confidence=0.9)
    if any(term in text for term in ("cafeteria", "alimentacao", "almoco", "servico da clinica")):
        return IntentClassification(domain=Domain.KNOWLEDGE, intent="institutional_knowledge", confidence=0.85)
    if any(term in text for term in ("politica", "orientacao", "instrucao", "documentos necessarios")):
        return IntentClassification(domain=Domain.KNOWLEDGE, intent="institutional_knowledge", confidence=0.85)
    return None
