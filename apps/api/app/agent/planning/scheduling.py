from __future__ import annotations

import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from app.agent.conversation import (
    AvailabilityDateQuestion,
    AvailabilitySlots,
    ConversationContext,
    PresentedSlot,
    SlotChoiceQuestion,
)
from app.agent.orchestration.dates import extract_availability_slots
from app.agent.planning.models import ExecutionPlan, PlanKind, PlanStep
from app.agent.presentation import response
from app.agent.routing.rules import normalize
from app.modules.catalog.application import CatalogService


def build_availability_plan(
    message: str, context: ConversationContext, today: date
) -> ExecutionPlan:
    updated = _availability_context(message, context, today)
    if updated.availability.from_date is None:
        return _missing_date_plan(updated)
    arguments: dict[str, object] = dict(updated.availability.tool_arguments())
    if pending := updated.pending_reschedule:
        arguments.update(
            {
                "doctor_id": pending.doctor_id,
                "reschedule_appointment_id": pending.appointment_id,
            }
        )
    return ExecutionPlan(
        kind=PlanKind.TOOL,
        steps=[PlanStep(tool_name="search_availability", arguments=arguments)],
        reason_codes=["authoritative_data:scheduling"],
        context=updated.with_pending_question(None).with_tool("search_availability"),
    )


def build_appointment_selection_plan(message: str, context: ConversationContext) -> ExecutionPlan:
    if context.presented_availability.is_expired():
        return _expired_slots_plan(context)
    matches = _matching_slots(message, context)
    if not matches:
        return _missing_slot_plan(context)
    if len(matches) > 1:
        return _ambiguous_slot_plan(matches, context)
    return _booking_plan(matches[0], context)


def _availability_context(
    message: str, context: ConversationContext, today: date
) -> ConversationContext:
    text = normalize(message)
    if any(term in text for term in ("outro dia", "outra data")):
        context = context.model_copy(update={"availability": AvailabilitySlots()})
    reference = today
    if _uses_previous_month(text, context):
        assert context.availability.from_date is not None
        reference = context.availability.from_date
    extracted = extract_availability_slots(message, reference)
    if extracted.from_date is None and _requests_available_days(text):
        extracted = extracted.model_copy(
            update={"from_date": today, "to_date": today + timedelta(days=14)}
        )
    entities = CatalogService().resolve_doctor_entities(message)
    doctor_id = _single(entities["doctor_ids"])
    if doctor_id is None and context.availability.doctor_id is None:
        doctor_id = _single(context.directory.doctor_ids)
    extracted = extracted.model_copy(
        update={
            "doctor_id": doctor_id,
            "specialty_id": _single(entities["specialty_ids"]),
            "unit_id": _single(entities["unit_ids"]),
            "insurer_id": _single(entities["insurer_ids"]),
        }
    )
    return context.with_availability(extracted)


def _missing_date_plan(context: ConversationContext) -> ExecutionPlan:
    return ExecutionPlan(
        kind=PlanKind.CLARIFICATION,
        response=response(
            "Claro! Para qual dia você gostaria de consultar os horários?",
            "clarify_availability",
            suggestions=_date_suggestions(),
        ),
        reason_codes=["missing_slot:availability.date"],
        context=context.with_pending_question(AvailabilityDateQuestion()),
    )


def _expired_slots_plan(context: ConversationContext) -> ExecutionPlan:
    cleared = context.presented_availability.model_copy(update={"slots": [], "expires_at": None})
    return ExecutionPlan(
        kind=PlanKind.CLARIFICATION,
        response=response(
            "Esses horários expiraram para evitar uma escolha desatualizada. Qual dia você quer consultar novamente?",
            "clarify_availability",
            suggestions=_date_suggestions(),
        ),
        reason_codes=["expired_context:presented_availability"],
        context=context.model_copy(
            update={
                "presented_availability": cleared,
                "pending_question": AvailabilityDateQuestion(),
            }
        ),
    )


def _missing_slot_plan(context: ConversationContext) -> ExecutionPlan:
    return ExecutionPlan(
        kind=PlanKind.CLARIFICATION,
        response=response(
            "Não consegui relacionar essa escolha aos horários exibidos. Qual opção você prefere?",
            "clarify_slot",
            suggestions=_slot_suggestions(context),
        ),
        reason_codes=["missing_slot:appointment.selection"],
        context=context.with_pending_question(SlotChoiceQuestion()),
    )


def _ambiguous_slot_plan(
    matches: list[PresentedSlot], context: ConversationContext
) -> ExecutionPlan:
    return ExecutionPlan(
        kind=PlanKind.CLARIFICATION,
        response=response(
            "Encontrei mais de uma opção nesse horário. Qual delas você prefere?",
            "clarify_slot",
            suggestions=_suggestions_for_slots(matches),
        ),
        reason_codes=["ambiguous_slot:appointment.selection"],
        context=context.with_pending_question(SlotChoiceQuestion()),
    )


def _booking_plan(slot: PresentedSlot, context: ConversationContext) -> ExecutionPlan:
    return ExecutionPlan(
        kind=PlanKind.TOOL,
        steps=[
            PlanStep(
                tool_name="create_appointment",
                arguments={
                    "doctor_id": slot.doctor_id,
                    "starts_at": slot.starts_at.isoformat(),
                    "reason": "Consulta",
                },
            )
        ],
        reason_codes=["context:presented_availability_slot"],
        context=context.with_pending_question(None).with_tool("create_appointment"),
    )


def _matching_slots(message: str, context: ConversationContext) -> list[PresentedSlot]:
    slots = context.presented_availability.slots
    text = normalize(message)
    position = _selected_position(text, len(slots))
    if position is not None:
        return [slot for slot in slots if slot.position == position]
    clock = re.search(r"\b(?:às|as|a)\s+(\d{1,2})(?::(\d{2}))?\b", message.casefold())
    if not clock:
        return []
    hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
    return [slot for slot in slots if _local_clock(slot) == (hour, minute)]


def _selected_position(text: str, slot_count: int) -> int | None:
    ordinals = {
        "primeiro": 1,
        "primeira": 1,
        "segundo": 2,
        "segunda opcao": 2,
        "terceiro": 3,
        "terceira": 3,
    }
    for label, position in ordinals.items():
        if label in text:
            return position
    if numbered := re.search(r"\bopcao\s+(\d{1,2})\b", text):
        return int(numbered.group(1))
    if "ultimo" in text or "ultima" in text:
        return slot_count or None
    return None


def _local_clock(slot: PresentedSlot) -> tuple[int, int]:
    local = slot.starts_at.astimezone(ZoneInfo(slot.timezone))
    return local.hour, local.minute


def _slot_suggestions(context: ConversationContext) -> list[dict[str, str]]:
    return _suggestions_for_slots(context.presented_availability.slots)


def _suggestions_for_slots(slots: list[PresentedSlot]) -> list[dict[str, str]]:
    return [
        {
            "label": f"{slot.position}. {slot.doctor_name} · {_local_clock(slot)[0]:02d}:{_local_clock(slot)[1]:02d}",
            "message": f"Quero a opção {slot.position}",
        }
        for slot in slots[:4]
    ]


def _date_suggestions() -> list[dict[str, str]]:
    return [
        {"label": "Amanhã", "message": "Quero horários para amanhã"},
        {
            "label": "Próxima sexta-feira",
            "message": "Quero horários na próxima sexta-feira",
        },
    ]


def _single(values: list[str]) -> str | None:
    return values[0] if len(values) == 1 else None


def _requests_available_days(text: str) -> bool:
    terms = (
        "quais dias",
        "proximos dias",
        "quando tem",
        "quando ha",
        "quando esta disponivel",
    )
    return any(term in text for term in terms)


def _uses_previous_month(text: str, context: ConversationContext) -> bool:
    return context.availability.from_date is not None and bool(
        re.search(r"\bdia\s+(?:\d{1,2}|[a-z]+(?:\s+e\s+[a-z]+)?)\b", text)
    )
