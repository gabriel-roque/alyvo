import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers import chat_provider
from app.ai.retrieval import retrieve
from app.models import Appointment, Doctor, Specialty, Unit
from app.routers.operations import available_slots

SYSTEM_PROMPT = """Você é a assistente administrativa da clínica Alyvo.
Considere todo o histórico da conversa e continue o fluxo iniciado pelo paciente.
Responda saudações e conversa casual naturalmente, sem chamar ferramentas.
Use search_knowledge apenas para dúvidas institucionais. Nunca use search_knowledge
para conduzir agendamento. Quando o paciente quiser marcar uma consulta, chame
search_availability imediatamente, mesmo que só haja médico, especialidade ou
nenhum filtro; datas ausentes significam os próximos 14 dias. Não exija motivo
antes de mostrar horários. O paciente escolherá um dos horários retornados antes
de create_appointment ser chamado. Se ele refinar data, médico ou unidade em uma
mensagem seguinte, preserve os critérios anteriores e chame search_availability novamente.
Use as ferramentas para consultar dados; nunca invente informações operacionais.
Não ofereça diagnóstico, prescrição ou triagem. Para ações pessoais, permita que
o servidor solicite identificação. Responda sempre em português brasileiro."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Busca informações institucionais aprovadas. Não use para saudações nem para agendamento.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_my_appointments",
            "description": "Lista as consultas do paciente identificado.",
            "parameters": {"type": "object", "properties": {"status": {"type": "string", "enum": ["confirmed", "cancelled"]}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_availability",
            "description": "Pesquisa horários para continuar um pedido de agendamento. Pode ser usada anonimamente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty": {"type": "string"},
                    "doctor": {"type": "string"},
                    "unit": {"type": "string"},
                    "from": {"type": "string", "format": "date"},
                    "to": {"type": "string", "format": "date"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_appointment",
            "description": "Agenda uma consulta para o paciente identificado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor_id": {"type": "string"},
                    "starts_at": {"type": "string", "format": "date-time"},
                    "reason": {"type": "string"},
                },
                "required": ["doctor_id", "starts_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancela uma consulta do paciente identificado.",
            "parameters": {
                "type": "object",
                "properties": {"appointment_id": {"type": "string"}},
                "required": ["appointment_id"],
            },
        },
    },
]


class KnowledgeArgs(BaseModel):
    query: str


class AppointmentListArgs(BaseModel):
    status: str | None = None


class AvailabilityArgs(BaseModel):
    specialty: str | None = None
    doctor: str | None = None
    unit: str | None = None
    from_: date | None = None
    to: date | None = None


def _base(answer: str, tool: str, **values) -> dict:
    return {
        "answer": answer,
        "intent": tool,
        "confidence": values.pop("confidence", 1.0),
        "citations": values.pop("citations", []),
        "auth_required": False,
        "confirmation_request": None,
        "tool_result": None,
        "tool_call": {"name": tool},
        **values,
    }


def execute_tool(db: Session, tenant_id: str, identity: dict | None, name: str, arguments: dict) -> dict:
    if name == "search_knowledge":
        query = KnowledgeArgs.model_validate(arguments).query
        result = retrieve(db, tenant_id, query)
        if result.confidence < 0.6:
            return _base("Não encontrei evidência suficiente na base aprovada. Entre em contato com a clínica para confirmar.", name, confidence=result.confidence)
        answer = chat_provider().complete(query, result.answer_context)
        return _base(answer, name, confidence=result.confidence, citations=result.citations)
    if name == "list_my_appointments":
        if not identity or identity.get("role") != "patient":
            return _base("Para consultar suas consultas, confirme seu CPF e sua data de nascimento.", name, auth_required=True, pending_tool={"name": name, "arguments": arguments})
        parsed = AppointmentListArgs.model_validate(arguments)
        query = select(Appointment).where(Appointment.tenant_id == tenant_id, Appointment.patient_id == identity["sub"])
        if parsed.status:
            query = query.where(Appointment.status == parsed.status)
        rows = db.scalars(query.order_by(Appointment.starts_at)).all()
        doctors = {item.id: item.name for item in db.scalars(select(Doctor).where(Doctor.tenant_id == tenant_id))}
        units = {item.id: item.name for item in db.scalars(select(Unit).where(Unit.tenant_id == tenant_id))}
        items = [{"id": item.id, "doctor": doctors.get(item.doctor_id), "unit": units.get(item.unit_id), "starts_at": item.starts_at.isoformat(), "status": item.status.value, "reason": item.reason} for item in rows]
        answer = "Estas são as suas consultas." if items else "Você não possui consultas nesse período."
        return _base(answer, name, tool_result={"type": "appointments", "items": items})
    if name == "search_availability":
        normalized = dict(arguments)
        normalized["from_"] = normalized.pop("from", None)
        parsed = AvailabilityArgs.model_validate(normalized)
        doctor_id = None
        specialty_id = None
        unit_id = None
        if parsed.doctor:
            doctor_id = db.scalar(select(Doctor.id).where(Doctor.tenant_id == tenant_id, Doctor.name.ilike(f"%{parsed.doctor}%"), Doctor.active.is_(True)))
            if not doctor_id:
                return _base(
                    f"Não encontrei um médico ativo com o nome “{parsed.doctor}”. Tente informar o nome completo ou a especialidade.",
                    name,
                    confidence=0.0,
                    tool_result={"type": "availability", "items": []},
                )
        if parsed.specialty:
            specialty_id = db.scalar(select(Specialty.id).where(Specialty.tenant_id == tenant_id, Specialty.name.ilike(f"%{parsed.specialty}%"), Specialty.active.is_(True)))
            if not specialty_id:
                return _base(
                    f"Não encontrei a especialidade “{parsed.specialty}”. Tente outro nome.",
                    name,
                    confidence=0.0,
                    tool_result={"type": "availability", "items": []},
                )
        if parsed.unit:
            unit_id = db.scalar(select(Unit.id).where(Unit.tenant_id == tenant_id, Unit.name.ilike(f"%{parsed.unit}%"), Unit.active.is_(True)))
            if not unit_id:
                return _base(
                    f"Não encontrei a unidade “{parsed.unit}”. Tente outro nome.",
                    name,
                    confidence=0.0,
                    tool_result={"type": "availability", "items": []},
                )
        start = parsed.from_ or datetime.now(timezone.utc).date()
        end = min(parsed.to or start + timedelta(days=14), start + timedelta(days=31))
        items = available_slots(db, tenant_id, start, end, doctor_id, specialty_id, unit_id)[:12]
        serialized = [{**item, "starts_at": item["starts_at"].isoformat(), "ends_at": item["ends_at"].isoformat()} for item in items]
        return _base("Encontrei estes horários disponíveis." if items else "Não encontrei horários com esses critérios.", name, tool_result={"type": "availability", "items": serialized})
    if name in {"create_appointment", "cancel_appointment"}:
        if not identity or identity.get("role") != "patient":
            return _base("Para continuar, confirme seu CPF e sua data de nascimento.", name, auth_required=True, pending_tool={"name": name, "arguments": arguments})
        return _base("Revise os dados antes de confirmar.", name, confirmation_request={"tool": name, "arguments": arguments})
    return _base("Não consegui executar essa solicitação.", "unknown", confidence=0.0)


def _greeting(message: str) -> str | None:
    normalized = re.sub(r"[^a-záàâãéêíóôõúç ]", "", message.casefold()).strip()
    greetings = {
        "oi": "Olá!",
        "olá": "Olá!",
        "ola": "Olá!",
        "bom dia": "Bom dia!",
        "boa tarde": "Boa tarde!",
        "boa noite": "Boa noite!",
        "tudo bem": "Olá! Tudo bem por aqui.",
        "oi tudo bem": "Olá! Tudo bem por aqui.",
        "olá tudo bem": "Olá! Tudo bem por aqui.",
        "ola tudo bem": "Olá! Tudo bem por aqui.",
    }
    prefix = greetings.get(normalized)
    if not prefix:
        return None
    return f"{prefix} Como posso ajudar? Posso consultar médicos, horários, exames, convênios ou suas consultas."


def run_workflow(
    db: Session,
    tenant_id: str,
    identity: dict | None,
    message: str,
    history: list[dict] | None = None,
) -> dict:
    lowered = message.casefold()
    greeting = _greeting(message)
    if greeting:
        return _base(greeting, "conversation")
    if any(term in lowered for term in ("diagnóstico", "diagnostico", "prescreva", "receita médica", "qual doença", "dor no peito")):
        return _base("Posso ajudar apenas com informações administrativas. Não faço diagnóstico, prescrição ou triagem. Em uma emergência, procure o serviço de urgência da sua região.", "clinical_safety")
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    turn = chat_provider().respond(
        [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\nData atual: {today}. Interprete datas relativas a partir dela."},
            *(history or []),
            {"role": "user", "content": message},
        ],
        TOOLS,
    )
    if not turn.tool_calls:
        return _base(turn.content or "Como posso ajudar com informações administrativas da clínica?", "conversation")
    call = turn.tool_calls[0]
    try:
        return execute_tool(db, tenant_id, identity, call.name, call.arguments)
    except ValidationError:
        return _base("Preciso de mais informações para concluir essa solicitação.", call.name, confidence=0.0)
