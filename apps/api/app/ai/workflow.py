from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

from langsmith import traceable
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.conversation import (
    DialogState,
    human_date,
    human_datetime,
    local_datetime,
    normalized_text,
    period_from_message,
    resolve_date_window,
    tenant_today,
)
from app.ai.providers import ToolCall, chat_provider
from app.ai.retrieval import retrieve
from app.ai.tracing import tool_span_inputs, tool_span_outputs
from app.models import Appointment, AvailabilityRule, Doctor, Exam, Insurer, Specialty, Tenant, Unit
from app.observability import record
from app.routers.operations import available_slots
from app.tools import TOOL_REGISTRY, provider_tools, validate_tool_arguments

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_insurers",
            "description": "Lista os convênios e planos cadastrados pela clínica.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_exams",
            "description": "Lista exames e procedimentos cadastrados pela clínica.",
            "parameters": {"type": "object", "properties": {"unit": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_specialties",
            "description": "Lista especialidades ativas.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_units",
            "description": "Lista unidades e endereços da clínica.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_directory",
            "description": "Consulta médicos, especialidades, unidades e convênios cadastrados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty": {"type": "string"},
                    "doctor": {"type": "string"},
                    "unit": {"type": "string"},
                    "insurer": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Busca políticas e orientações institucionais aprovadas.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_my_appointments",
            "description": "Lista as consultas do paciente identificado.",
            "parameters": {
                "type": "object",
                "properties": {"status": {"type": "string", "enum": ["confirmed", "cancelled"]}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_availability",
            "description": "Pesquisa horários reais na agenda da clínica.",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty": {"type": "string"},
                    "doctor": {"type": "string"},
                    "unit": {"type": "string"},
                    "insurer": {"type": "string"},
                    "period": {"type": "string", "enum": ["morning", "afternoon", "evening"]},
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
            "description": "Agenda a opção escolhida para o paciente identificado.",
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
ALLOWED_TOOLS: set[str] = set()

# The typed registry is the source of truth. The assignment stays close to the
# previous declaration so provider behavior remains backward compatible.
TOOLS = provider_tools()
ALLOWED_TOOLS = set(TOOL_REGISTRY)


class KnowledgeArgs(BaseModel):
    query: str


class DirectoryArgs(BaseModel):
    specialty: str | None = None
    doctor: str | None = None
    unit: str | None = None
    insurer: str | None = None
    include_address: bool = False


class AppointmentListArgs(BaseModel):
    status: str | None = None


class AvailabilityArgs(DirectoryArgs):
    period: str | None = None
    from_: date | None = None
    to: date | None = None
    offset: int = 0
    refinement: bool = False


def _base(answer: str, tool: str, **values: Any) -> dict[str, Any]:
    return {
        "answer": answer,
        "intent": tool,
        "confidence": values.pop("confidence", 1.0),
        "citations": values.pop("citations", []),
        "auth_required": False,
        "confirmation_request": None,
        "tool_result": None,
        "tool_call": {"name": tool},
        "suggestions": values.pop("suggestions", []),
        "resolved_request": values.pop("resolved_request", None),
        **values,
    }


def _timezone(db: Session, tenant_id: str) -> str:
    tenant = db.get(Tenant, tenant_id)
    return tenant.timezone if tenant else "America/Sao_Paulo"


def _find_id(db: Session, model, tenant_id: str, name: str | None) -> str | None:
    if not name:
        return None
    return db.scalar(
        select(model.id).where(
            model.tenant_id == tenant_id,
            model.name.ilike(f"%{name}%"),
            model.active.is_(True),
        )
    )


def _directory(db: Session, tenant_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    parsed = DirectoryArgs.model_validate(arguments)
    if parsed.include_address:
        units_query = select(Unit).where(
            Unit.tenant_id == tenant_id,
            Unit.active.is_(True),
        )
        if parsed.unit:
            units_query = units_query.where(Unit.name.ilike(f"%{parsed.unit}%"))
        units = db.scalars(units_query.order_by(Unit.name)).all()
        if not units:
            return _base(
                "Não encontrei essa unidade. Você pode conferir o nome?",
                "search_directory",
                confidence=0.0,
            )
        details = "; ".join(f"{unit.name}: {unit.address}" for unit in units)
        return _base(
            f"{details}.",
            "search_directory",
            tool_result={
                "type": "units",
                "items": [
                    {"id": unit.id, "unit": unit.name, "address": unit.address} for unit in units
                ],
            },
            resolved_request={"unit": parsed.unit, "include_address": True},
        )
    query = (
        select(Doctor, Specialty, Unit)
        .join(Specialty, Doctor.specialty_id == Specialty.id)
        .join(Unit, Doctor.unit_id == Unit.id)
        .where(Doctor.tenant_id == tenant_id, Doctor.active.is_(True), Doctor.deleted_at.is_(None))
    )
    if parsed.doctor:
        query = query.where(Doctor.name.ilike(f"%{parsed.doctor}%"))
    if parsed.specialty:
        query = query.where(Specialty.name.ilike(f"%{parsed.specialty}%"))
    if parsed.unit:
        query = query.where(Unit.name.ilike(f"%{parsed.unit}%"))
    insurers = {
        item.id: item.name
        for item in db.scalars(
            select(Insurer).where(Insurer.tenant_id == tenant_id, Insurer.active.is_(True))
        )
    }
    insurer_id = _find_id(db, Insurer, tenant_id, parsed.insurer)
    rows: list[dict[str, Any]] = []
    for doctor, specialty, unit in db.execute(query.order_by(Doctor.name)):
        if parsed.insurer and (not insurer_id or insurer_id not in doctor.insurer_ids):
            continue
        rows.append(
            {
                "id": doctor.id,
                "doctor": doctor.name,
                "crm": doctor.crm,
                "specialty": specialty.name,
                "unit": unit.name,
                "insurers": [insurers[item] for item in doctor.insurer_ids if item in insurers],
            }
        )
    if not rows:
        return _base(
            "Não encontrei profissionais com esses critérios. Posso tentar outra especialidade, unidade ou convênio.",
            "search_directory",
            confidence=0.0,
            tool_result={"type": "directory", "items": []},
            suggestions=[
                {"label": "Ver todos os médicos", "message": "Quais médicos atendem na clínica?"}
            ],
        )
    names = ", ".join(item["doctor"] for item in rows[:3])
    return _base(
        f"Encontrei {len(rows)} {'profissional' if len(rows) == 1 else 'profissionais'}: {names}.",
        "search_directory",
        tool_result={"type": "directory", "items": rows},
        suggestions=[{"label": "Ver horários", "message": "Quero ver os horários disponíveis"}],
        resolved_request=parsed.model_dump(exclude_none=True),
    )


@traceable(
    name="alyvo.tool.execute",
    run_type="tool",
    process_inputs=tool_span_inputs,
    process_outputs=tool_span_outputs,
)
def execute_tool(
    db: Session,
    tenant_id: str,
    identity: dict[str, Any] | None,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    if name not in ALLOWED_TOOLS:
        return _base(
            "Não consegui executar essa solicitação com segurança.", "unknown", confidence=0.0
        )
    arguments = validate_tool_arguments(name, arguments)
    try:
        if name == "list_insurers":
            insurer_items = db.scalars(
                select(Insurer)
                .where(Insurer.tenant_id == tenant_id, Insurer.active.is_(True))
                .order_by(Insurer.name)
            ).all()
            insurer_names = ", ".join(item.name for item in insurer_items)
            return _base(
                f"Atendemos {insurer_names}."
                if insurer_items
                else "Não encontrei convênios ativos cadastrados.",
                name,
                tool_result={
                    "type": "insurers",
                    "items": [{"id": item.id, "name": item.name} for item in insurer_items],
                },
                confidence=1.0 if insurer_items else 0.0,
            )
        if name == "list_exams":
            exam_query = select(Exam).where(Exam.tenant_id == tenant_id, Exam.active.is_(True))
            unit_name = arguments.get("unit")
            unit_id = _find_id(db, Unit, tenant_id, unit_name)
            exam_items = db.scalars(exam_query.order_by(Exam.name)).all()
            exam_units = {
                item.id: item
                for item in db.scalars(
                    select(Unit).where(Unit.tenant_id == tenant_id, Unit.active.is_(True))
                )
            }
            exam_rows: list[dict[str, Any]] = []
            for exam in exam_items:
                exam_unit_ids = list(getattr(exam, "unit_ids", []) or [])
                if unit_name and (not unit_id or unit_id not in exam_unit_ids):
                    continue
                exam_rows.append(
                    {
                        "id": exam.id,
                        "name": exam.name,
                        "units": [
                            {"id": item_id, "name": exam_units[item_id].name}
                            for item_id in exam_unit_ids
                            if item_id in exam_units
                        ],
                    }
                )
            exam_names = ", ".join(str(item["name"]) for item in exam_rows)
            return _base(
                f"Realizamos {exam_names}."
                if exam_rows
                else "Não encontrei exames ativos com esses critérios.",
                name,
                tool_result={"type": "exams", "items": exam_rows},
                confidence=1.0 if exam_rows else 0.0,
            )
        if name == "list_specialties":
            specialty_items = db.scalars(
                select(Specialty)
                .where(Specialty.tenant_id == tenant_id, Specialty.active.is_(True))
                .order_by(Specialty.name)
            ).all()
            return _base(
                f"Temos atendimento em {', '.join(item.name for item in specialty_items)}."
                if specialty_items
                else "Não encontrei especialidades ativas.",
                name,
                tool_result={
                    "type": "specialties",
                    "items": [{"id": item.id, "name": item.name} for item in specialty_items],
                },
                confidence=1.0 if specialty_items else 0.0,
            )
        if name == "list_units":
            unit_items = db.scalars(
                select(Unit)
                .where(Unit.tenant_id == tenant_id, Unit.active.is_(True))
                .order_by(Unit.name)
            ).all()
            return _base(
                f"Nossas unidades são: {', '.join(item.name for item in unit_items)}."
                if unit_items
                else "Não encontrei unidades ativas.",
                name,
                tool_result={
                    "type": "units",
                    "items": [
                        {"id": item.id, "name": item.name, "address": item.address}
                        for item in unit_items
                    ],
                },
                confidence=1.0 if unit_items else 0.0,
            )
        if name == "search_directory":
            return _directory(db, tenant_id, arguments)
        if name == "search_knowledge":
            knowledge_query = KnowledgeArgs.model_validate(arguments).query
            result = retrieve(db, tenant_id, knowledge_query)
            if result.confidence < 0.6:
                return _base(
                    "Não encontrei essa informação na base aprovada. Posso ajudar com outra dúvida ou você pode confirmar diretamente com a clínica.",
                    name,
                    confidence=result.confidence,
                    suggestions=[
                        {"label": "Ver o que posso fazer", "message": "Como você pode me ajudar?"}
                    ],
                )
            return _base(
                chat_provider().complete(knowledge_query, result.answer_context),
                name,
                confidence=result.confidence,
                citations=result.citations,
            )
        if name == "list_my_appointments":
            if not identity or identity.get("role") != "patient":
                return _base(
                    "Para consultar suas consultas com segurança, confirme seu CPF e sua data de nascimento.",
                    name,
                    auth_required=True,
                    pending_tool={"name": name, "arguments": arguments},
                )
            appointment_args = AppointmentListArgs.model_validate(arguments)
            appointment_query = select(Appointment).where(
                Appointment.tenant_id == tenant_id,
                Appointment.patient_id == identity["sub"],
            )
            if appointment_args.status:
                appointment_query = appointment_query.where(
                    Appointment.status == appointment_args.status
                )
            if appointment_args.status != "cancelled":
                appointment_query = appointment_query.where(
                    Appointment.starts_at >= datetime.now(timezone.utc)
                )
            appointment_rows = db.scalars(appointment_query.order_by(Appointment.starts_at)).all()
            doctor_names = {
                item.id: item.name
                for item in db.scalars(select(Doctor).where(Doctor.tenant_id == tenant_id))
            }
            unit_names = {
                item.id: item.name
                for item in db.scalars(select(Unit).where(Unit.tenant_id == tenant_id))
            }
            timezone_name = _timezone(db, tenant_id)
            appointment_items: list[dict[str, Any]] = [
                {
                    "id": item.id,
                    "doctor": doctor_names.get(item.doctor_id),
                    "unit": unit_names.get(item.unit_id),
                    "starts_at": local_datetime(item.starts_at, timezone_name).isoformat(),
                    "status": item.status.value,
                    "reason": item.reason,
                }
                for item in appointment_rows[:5]
            ]
            appointment_label = (
                f"{'consulta cancelada' if len(appointment_rows) == 1 else 'consultas canceladas'}"
                if appointment_args.status == "cancelled"
                else f"{'consulta futura confirmada' if len(appointment_rows) == 1 else 'consultas futuras confirmadas'}"
            )
            answer = (
                f"Encontrei {len(appointment_rows)} {appointment_label}."
                if appointment_items
                else "Você não possui consultas com esse status."
            )
            if len(appointment_rows) > len(appointment_items):
                answer += f" Estou mostrando as próximas {len(appointment_items)}."
            return _base(
                answer,
                name,
                tool_result={
                    "type": "appointments",
                    "items": appointment_items,
                    "timezone": timezone_name,
                    "total": len(appointment_rows),
                    "has_more": len(appointment_rows) > len(appointment_items),
                },
            )
        if name == "search_availability":
            normalized = dict(arguments)
            normalized["from_"] = normalized.pop("from", None)
            availability_args = AvailabilityArgs.model_validate(normalized)
            doctor_id = _find_id(db, Doctor, tenant_id, availability_args.doctor)
            specialty_id = _find_id(db, Specialty, tenant_id, availability_args.specialty)
            unit_id = _find_id(db, Unit, tenant_id, availability_args.unit)
            insurer_id = _find_id(db, Insurer, tenant_id, availability_args.insurer)
            for value, resolved, label in (
                (availability_args.doctor, doctor_id, "médico"),
                (availability_args.specialty, specialty_id, "especialidade"),
                (availability_args.unit, unit_id, "unidade"),
                (availability_args.insurer, insurer_id, "convênio"),
            ):
                if value and not resolved:
                    return _base(
                        f"Não encontrei o {label} “{value}”. Você pode conferir o nome ou tentar outro critério.",
                        name,
                        confidence=0.0,
                        tool_result={"type": "availability", "items": [], "total": 0},
                    )
            timezone_name = _timezone(db, tenant_id)
            start = availability_args.from_ or tenant_today(timezone_name)
            end = min(
                availability_args.to or start + timedelta(days=14),
                start + timedelta(days=31),
            )
            all_slots = available_slots(
                db,
                tenant_id,
                start,
                end,
                doctor_id,
                specialty_id,
                unit_id,
                insurer_id,
                availability_args.period,
            )
            offset = max(availability_args.offset, 0)
            visible_slots = all_slots[offset : offset + 4]
            serialized_slots = [
                {
                    **item,
                    "starts_at": local_datetime(item["starts_at"], timezone_name).isoformat(),
                    "ends_at": local_datetime(item["ends_at"], timezone_name).isoformat(),
                }
                for item in visible_slots
            ]
            date_summary = (
                human_date(start)
                if start == end
                else f"entre {human_date(start)} e {human_date(end)}"
            )
            criteria: list[str] = [date_summary]
            if availability_args.specialty:
                criteria.append(availability_args.specialty)
            if availability_args.doctor:
                criteria.append(availability_args.doctor)
            if availability_args.unit:
                criteria.append(availability_args.unit)
            if availability_args.insurer:
                criteria.append(f"convênio {availability_args.insurer}")
            period_label = {
                "morning": "pela manhã",
                "afternoon": "à tarde",
                "evening": "à noite",
            }.get(availability_args.period or "")
            if period_label:
                criteria.append(period_label)
            request_summary = ", ".join(criteria)
            prefix = (
                "Atualizei os horários" if availability_args.refinement else "Encontrei horários"
            )
            answer = (
                f"{prefix} para {request_summary}. Veja as opções abaixo."
                if visible_slots
                else f"Não encontrei horários para {request_summary}. Posso ajustar um dos critérios."
            )
            filters = availability_args.model_dump(
                exclude_none=True,
                exclude={"include_address", "offset", "refinement"},
            )
            filters.pop("from_", None)
            filters["from"] = start.isoformat()
            filters["to"] = end.isoformat()
            suggestions: list[dict[str, str]] = []
            if offset + len(visible_slots) < len(all_slots):
                suggestions.append(
                    {"label": "Ver mais horários", "message": "Mostre mais horários"}
                )
            if availability_args.period != "afternoon":
                suggestions.append(
                    {"label": "Somente à tarde", "message": "Mostre somente os horários à tarde"}
                )
            other_unit = db.scalar(
                select(Unit)
                .where(
                    Unit.tenant_id == tenant_id,
                    Unit.active.is_(True),
                    Unit.id != unit_id if unit_id else Unit.id.is_not(None),
                )
                .order_by(Unit.name)
            )
            if other_unit:
                suggestions.append(
                    {
                        "label": other_unit.name,
                        "message": f"Procure na {other_unit.name}",
                    }
                )
            return _base(
                answer,
                name,
                tool_result={
                    "type": "availability",
                    "items": serialized_slots,
                    "total": len(all_slots),
                    "has_more": offset + len(visible_slots) < len(all_slots),
                    "timezone": timezone_name,
                    "query_summary": request_summary,
                },
                suggestions=suggestions,
                resolved_request=filters,
            )
        if name in {"create_appointment", "cancel_appointment"}:
            if not identity or identity.get("role") != "patient":
                return _base(
                    "Para continuar com segurança, confirme seu CPF e sua data de nascimento.",
                    name,
                    auth_required=True,
                    pending_tool={"name": name, "arguments": arguments},
                )
            summary = "Confira os dados antes de confirmar."
            if name == "create_appointment":
                doctor = db.get(Doctor, arguments.get("doctor_id"))
                starts_at = arguments.get("starts_at")
                if doctor and starts_at:
                    parsed_datetime = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
                    unit = db.get(Unit, doctor.unit_id)
                    summary = (
                        f"{doctor.name}, {unit.name if unit else 'unidade informada'}, "
                        f"{human_datetime(parsed_datetime, _timezone(db, tenant_id))}."
                    )
            else:
                appointment = db.scalar(
                    select(Appointment).where(
                        Appointment.id == arguments.get("appointment_id"),
                        Appointment.tenant_id == tenant_id,
                        Appointment.patient_id == identity["sub"],
                    )
                )
                if not appointment:
                    return _base(
                        "Não encontrei essa consulta no seu cadastro.",
                        name,
                        confidence=0.0,
                    )
                doctor = db.get(Doctor, appointment.doctor_id)
                unit = db.get(Unit, appointment.unit_id)
                summary = (
                    f"Cancelar a consulta com {doctor.name if doctor else 'o profissional'}, "
                    f"na {unit.name if unit else 'unidade informada'}, "
                    f"{human_datetime(appointment.starts_at, _timezone(db, tenant_id))}?"
                )
            return _base(
                "Tudo certo. Revise os dados abaixo antes de concluir.",
                name,
                confirmation_request={"tool": name, "arguments": arguments, "summary": summary},
            )
    finally:
        record(
            "tool.execute",
            tool=name,
            tenant_id=tenant_id,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
    return _base("Não consegui executar essa solicitação.", "unknown", confidence=0.0)


def _schedule_information(db: Session, tenant_id: str, message: str) -> dict | None:
    text = normalized_text(message)
    if any(term in text for term in ("feriado", "sabado", "domingo", "fim de semana")):
        return None
    timezone_question = any(term in text for term in ("fuso", "sao paulo", "timezone"))
    hours_question = any(
        term in text for term in ("abre", "fecha", "funcionamento", "atendimento comeca")
    )
    if not timezone_question and not hours_question:
        return None
    rules = db.scalars(
        select(AvailabilityRule).where(
            AvailabilityRule.tenant_id == tenant_id,
            AvailabilityRule.active.is_(True),
        )
    ).all()
    parts = []
    if timezone_question:
        parts.append(
            "Sim. Todos os horários são exibidos no horário de São Paulo, o mesmo horário de Brasília"
        )
    if hours_question and rules:
        starts_at = min(rule.starts_at for rule in rules)
        ends_at = max(rule.ends_at for rule in rules)
        parts.append(
            f"Na agenda cadastrada, os atendimentos vão das {starts_at:%H:%M} às {ends_at:%H:%M} em dias úteis"
        )
    elif hours_question:
        parts.append(
            "Não encontrei o horário de funcionamento cadastrado; confirme diretamente com a clínica"
        )
    return _base(". ".join(parts) + ".", "schedule_information")


class CatalogEntry(Protocol):
    name: str


def _match_catalog(
    db: Session, tenant_id: str, message: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    text = normalized_text(message)
    text_tokens = set(text.split())
    enriched = dict(arguments)

    def match(
        items: Sequence[CatalogEntry],
        key: str,
        minimum_length: int,
        match_by_token: bool,
    ) -> None:
        for item in items:
            candidate = normalized_text(item.name)
            identifying_tokens = [
                token
                for token in candidate.split()
                if len(token) >= minimum_length and token not in {"doutora", "doutor", "unidade"}
            ]
            token_match = match_by_token and any(
                token in text_tokens for token in identifying_tokens
            )
            if candidate in text or token_match:
                enriched[key] = item.name
                break

    match(
        db.scalars(select(Doctor).where(Doctor.tenant_id == tenant_id)).all(),
        "doctor",
        4,
        True,
    )
    match(
        db.scalars(select(Specialty).where(Specialty.tenant_id == tenant_id)).all(),
        "specialty",
        4,
        False,
    )
    match(
        db.scalars(select(Unit).where(Unit.tenant_id == tenant_id)).all(),
        "unit",
        3,
        True,
    )
    match(
        db.scalars(select(Insurer).where(Insurer.tenant_id == tenant_id)).all(),
        "insurer",
        4,
        False,
    )
    if "cardiolog" in text or "cardeolog" in text:
        enriched["specialty"] = "Cardiologia"
    elif "pediatr" in text:
        enriched["specialty"] = "Pediatria"
    return enriched


def _merge_state(
    db: Session, tenant_id: str, message: str, call: ToolCall, state: DialogState
) -> tuple[ToolCall, DialogState]:
    arguments = _match_catalog(db, tenant_id, message, call.arguments)
    if call.name == "search_availability":
        was_refinement = state.active_intent == "search_availability"
        previous = state.filters.model_dump(exclude_none=True)
        if arguments.get("specialty") and arguments.get("specialty") != previous.get("specialty"):
            previous.pop("doctor", None)
            state.filters.doctor = None
        if arguments.get("doctor") and arguments.get("doctor") != previous.get("doctor"):
            previous.pop("specialty", None)
            state.filters.specialty = None
        previous.update(arguments)
        previous.pop("start_date", None)
        previous.pop("end_date", None)
        window = resolve_date_window(message, _timezone(db, tenant_id))
        if window:
            previous["from"] = window.start.isoformat()
            previous["to"] = window.end.isoformat()
            state.filters.start_date = window.start
            state.filters.end_date = window.end
        elif state.filters.start_date:
            previous["from"] = state.filters.start_date.isoformat()
            previous["to"] = (state.filters.end_date or state.filters.start_date).isoformat()
        period = period_from_message(message)
        if period:
            previous["period"] = period
            state.filters.period = period
        text = normalized_text(message)
        changed_filters = bool(
            window
            or period
            or any(arguments.get(key) for key in ("specialty", "doctor", "unit", "insurer"))
        )
        if "mais horarios" in text:
            state.availability_offset += 4
        elif changed_filters or not was_refinement:
            state.availability_offset = 0
        previous["offset"] = state.availability_offset
        previous["refinement"] = was_refinement
        for key in ("specialty", "doctor", "unit", "insurer"):
            setattr(state.filters, key, previous.get(key))
        arguments = previous
    elif call.name == "search_directory":
        for key in ("specialty", "doctor", "unit", "insurer"):
            if arguments.get(key):
                setattr(state.filters, key, arguments[key])
    state.active_intent = call.name
    return ToolCall(call.name, arguments), state


def run_workflow(
    db: Session,
    tenant_id: str,
    identity: dict | None,
    message: str,
    history: list[dict] | None = None,
    session_state: dict | None = None,
    thread_id: str = "anonymous",
) -> dict:
    from app.ai.graph import run_graph

    return run_graph(
        db,
        tenant_id,
        identity,
        message,
        history,
        session_state,
        thread_id,
    )
