from __future__ import annotations

import json
from contextvars import ContextVar
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langsmith import tracing_context
from pydantic import ValidationError

from app.ai.checkpoints import checkpointer
from app.ai.conversation import (
    DialogState,
    normalized_text,
    period_from_message,
    resolve_date_window,
)
from app.ai.intents import Domain, IntentClassification, RiskLevel, deterministic_classification
from app.ai.privacy import redact_text, safe_trace_metadata
from app.ai.providers import chat_provider
from app.ai.workflow import (
    SYSTEM_PROMPT,
    ToolCall,
    _base,
    _match_catalog,
    _merge_state,
    _schedule_information,
    execute_tool,
)
from app.config import get_settings
from app.observability import record


class GraphState(TypedDict, total=False):
    message: str
    normalized: str
    history: list[dict]
    legacy_state: dict
    dialog: dict
    classification: dict
    tool_name: str
    tool_arguments: dict
    result: dict


class ActionGraphState(TypedDict, total=False):
    tool_name: str
    tool_arguments: dict
    confirmation_id: str
    result: dict


CLASSIFICATION_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_intent",
        "description": "Classifica uma solicitação administrativa de clínica sem responder ao usuário.",
        "parameters": IntentClassification.model_json_schema(),
    },
}

graph_runtime_context: ContextVar[tuple] = ContextVar("graph_runtime_context")


def _runtime() -> tuple:
    return graph_runtime_context.get()


def normalize_node(state: GraphState) -> dict:
    message = redact_text(state["message"])
    return {"message": message, "normalized": normalized_text(message)}


def classify_node(state: GraphState) -> dict:
    classification = deterministic_classification(state["message"])
    dialog = state.get("dialog") or {}
    if (
        classification is None
        and dialog.get("active_intent") == "search_availability"
        and (
            resolve_date_window(state["message"]) is not None
            or period_from_message(state["message"]) is not None
            or any(
                term in state["normalized"]
                for term in ("unidade", "centro", "sul", "mais horarios", "convenio")
            )
        )
    ):
        classification = IntentClassification(
            domain=Domain.SCHEDULING,
            intent="search_availability",
            action="search",
            confidence=0.98,
        )
    if classification is None:
        try:
            turn = chat_provider().respond(
                [
                    {
                        "role": "system",
                        "content": (
                            f"{SYSTEM_PROMPT}\nClassifique a mensagem usando classify_intent. "
                            "Reconheça pedidos não suportados e marque unsupported_reason."
                        ),
                    },
                    *state.get("history", [])[-6:],
                    {"role": "user", "content": state["message"]},
                ],
                [CLASSIFICATION_TOOL],
            )
            call = next((item for item in turn.tool_calls if item.name == "classify_intent"), None)
            classification = IntentClassification.model_validate(call.arguments) if call else None
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError):
            classification = None
    if classification is None:
        classification = IntentClassification(
            domain=Domain.FALLBACK,
            intent="ambiguous_request",
            confidence=0.35,
            needs_clarification=True,
        )
    payload = classification.model_dump(mode="json")
    record("intent.classified", **safe_trace_metadata(payload))
    return {"classification": payload}


def prepare_node(state: GraphState) -> dict:
    db, tenant_id, _identity = _runtime()
    classification = IntentClassification.model_validate(state["classification"])
    message = state["message"]

    try:
        dialog = DialogState.model_validate(state.get("dialog") or {})
    except ValidationError:
        dialog = DialogState()

    immediate: dict | None = None
    call: ToolCall | None = None
    if classification.domain == Domain.CLINICAL_SAFETY:
        if classification.risk_level == RiskLevel.URGENT:
            answer = (
                "Não consigo avaliar sintomas ou fazer triagem. Se você acredita que há risco imediato, "
                "procure agora um serviço de urgência ou emergência da sua região."
            )
        else:
            answer = (
                "Posso ajudar somente com informações administrativas. Não faço diagnóstico, "
                "prescrição nem interpretação clínica; converse com um profissional de saúde. "
                "Se houver uma urgência, procure o serviço de emergência da sua região."
            )
        immediate = _base(answer, "clinical_safety")
    elif classification.domain == Domain.SECURITY:
        immediate = _base(
            "Não posso acessar ou revelar dados de outra pessoa nem ignorar as regras de segurança.",
            "security",
        )
    elif classification.intent == "greeting":
        normalized = state["normalized"]
        greeting = "Bom dia" if "bom dia" in normalized else "Boa tarde" if "boa tarde" in normalized else "Boa noite" if "boa noite" in normalized else "Olá"
        immediate = _base(
            f"{greeting}! Como posso ajudar você hoje?",
            "conversation",
            suggestions=[
                {"label": "Ver horários", "message": "Quero ver horários disponíveis"},
                {"label": "Ver convênios", "message": "Quais convênios vocês atendem?"},
            ],
        )
    elif classification.intent == "thanks":
        immediate = _base("Por nada! Se precisar, posso ajudar com agenda e informações da clínica.", "conversation")
    elif classification.intent == "farewell":
        immediate = _base("Até logo! Quando precisar, estarei por aqui.", "conversation")
    elif classification.intent == "capabilities":
        immediate = _base(
            "Posso informar médicos, especialidades, unidades, convênios e exames; consultar horários; "
            "ajudar no agendamento; e responder orientações administrativas aprovadas pela clínica.",
            "capabilities",
            suggestions=[
                {"label": "Ver médicos", "message": "Quais médicos atendem?"},
                {"label": "Ver exames", "message": "Quais exames vocês realizam?"},
            ],
        )
    elif classification.unsupported_reason:
        immediate = _base(
            f"{classification.unsupported_reason} Posso ajudar com outra informação administrativa.",
            classification.intent,
            confidence=classification.confidence,
        )
    elif classification.intent == "list_insurers":
        call = ToolCall("list_insurers", {})
    elif classification.intent == "list_exams":
        call = ToolCall("list_exams", {})
    elif classification.intent == "list_specialties":
        call = ToolCall("list_specialties", {})
    elif classification.intent == "list_units":
        call = ToolCall("list_units", {})
    elif classification.intent == "unit_location":
        call = ToolCall("search_directory", {"include_address": True})
    elif classification.intent in {"list_doctors", "search_doctors_by_insurer"}:
        call = ToolCall("search_directory", {})
    elif classification.intent == "search_availability":
        call = ToolCall("search_availability", {})
    elif classification.intent == "list_my_appointments":
        call = ToolCall("list_my_appointments", {"status": "confirmed"})
    elif classification.intent == "cancel_appointment":
        call = ToolCall("list_my_appointments", {"status": "confirmed"})
    elif classification.intent == "opening_hours":
        immediate = _schedule_information(db, tenant_id, message)
        if immediate is None:
            call = ToolCall("search_knowledge", {"query": message})
    elif classification.domain in {Domain.EXAMS, Domain.KNOWLEDGE, Domain.INSTITUTIONAL}:
        query = message
        if classification.intent in {"exam_preparation", "institutional_knowledge"} and any(
            term in state["normalized"]
            for term in ("jejum", "preparo", "carteirinha", "recepcao", "documento")
        ):
            query = f"preparo exame pedido médico documento carteirinha recepção {message}"
        call = ToolCall("search_knowledge", {"query": query})
    elif classification.needs_clarification:
        immediate = _base(
            "Não entendi com segurança o que você precisa. Você procura médico, convênio, exame ou horário?",
            "clarification",
            confidence=classification.confidence,
        )
    else:
        immediate = _base(
            "Essa solicitação ainda não está disponível. Posso ajudar com agenda e informações administrativas.",
            "unsupported",
            confidence=classification.confidence,
        )

    if immediate is not None:
        immediate["dialog_state"] = dialog.model_dump(mode="json")
        return {"result": immediate, "dialog": dialog.model_dump(mode="json")}
    assert call is not None
    call = ToolCall(call.name, _match_catalog(db, tenant_id, message, call.arguments))
    call, dialog = _merge_state(db, tenant_id, message, call, dialog)
    return {
        "tool_name": call.name,
        "tool_arguments": call.arguments,
        "dialog": dialog.model_dump(mode="json"),
    }


def route_after_prepare(state: GraphState) -> str:
    return "finish" if state.get("result") else "execute"


def execute_node(state: GraphState) -> dict:
    db, tenant_id, identity = _runtime()
    name = state["tool_name"]
    arguments = state.get("tool_arguments", {})
    if name == "search_availability" and not arguments.get("from"):
        details = []
        if arguments.get("doctor"):
            details.append(f"com {arguments['doctor']}")
        elif arguments.get("specialty"):
            details.append(f"de {arguments['specialty']}")
        period_label = {
            "morning": "pela manhã",
            "afternoon": "à tarde",
            "evening": "à noite",
        }.get(arguments.get("period"))
        if period_label:
            details.append(period_label)
        suffix = f" {' '.join(details)}" if details else ""
        result = _base(
            f"Para qual dia você quer ver os horários{suffix}?",
            name,
            suggestions=[
                {"label": "Hoje", "message": "Hoje"},
                {"label": "Amanhã", "message": "Amanhã"},
                {"label": "Sexta-feira", "message": "Na sexta-feira"},
            ],
            resolved_request={
                key: value
                for key, value in arguments.items()
                if key in {"specialty", "doctor", "unit", "insurer", "period"} and value
            },
        )
    else:
        result = execute_tool(db, tenant_id, identity, name, arguments)
    result["dialog_state"] = state.get("dialog", {})
    return {"result": result}


def validate_node(state: GraphState) -> dict:
    result = dict(state["result"])
    operational = result.get("tool_call", {}).get("name") in {
        "list_insurers", "list_exams", "list_specialties", "list_units",
        "search_directory", "search_availability", "list_my_appointments",
    }
    if (
        operational
        and result.get("confidence", 1) > 0
        and not result.get("tool_result")
        and not result.get("auth_required")
        and not result.get("suggestions")
    ):
        result = _base(
            "Não consegui confirmar essa informação nos dados da clínica.",
            "evidence_missing",
            confidence=0,
        )
    return {"result": result}


def _build_graph(checkpointer):
    builder = StateGraph(GraphState)
    builder.add_node("normalize", normalize_node)
    builder.add_node("classify_intent", classify_node)
    builder.add_node("prepare_route", prepare_node)
    builder.add_node("execute_tool", execute_node)
    builder.add_node("validate_evidence", validate_node)
    builder.add_edge(START, "normalize")
    builder.add_edge("normalize", "classify_intent")
    builder.add_edge("classify_intent", "prepare_route")
    builder.add_conditional_edges(
        "prepare_route",
        route_after_prepare,
        {"execute": "execute_tool", "finish": "validate_evidence"},
    )
    builder.add_edge("execute_tool", "validate_evidence")
    builder.add_edge("validate_evidence", END)
    return builder.compile(checkpointer=checkpointer)


def confirm_action_node(state: ActionGraphState) -> dict:
    db, tenant_id, identity = _runtime()
    name = state["tool_name"]
    arguments = state.get("tool_arguments", {})
    prepared = execute_tool(db, tenant_id, identity, name, arguments)
    confirmation = prepared.get("confirmation_request")
    if confirmation is None:
        return {"result": prepared}

    accepted = interrupt(
        {
            "id": state["confirmation_id"],
            "tool": name,
            "summary": confirmation.get(
                "summary", "Confirme para concluir esta operação."
            ),
        }
    )
    if not accepted:
        answer = (
            "O cancelamento foi interrompido. Sua consulta continua confirmada."
            if name == "cancel_appointment"
            else "O agendamento não foi concluído."
        )
        return {"result": _base(answer, name, tool_call={"name": name})}

    # Import local keeps the operational router independent during app startup.
    from app.routers.operations import (
        AppointmentCreate,
        cancel_patient_appointment,
        create_patient_appointment,
    )

    if name == "create_appointment":
        appointment = create_patient_appointment(
            AppointmentCreate(
                doctor_id=arguments["doctor_id"],
                starts_at=arguments["starts_at"],
                reason=arguments.get("reason", "Consulta"),
                confirmed=True,
            ),
            identity,
            db,
        )
        result = _base(
            "Consulta agendada com sucesso.",
            name,
            tool_result={"type": "appointment_created", "appointment": appointment},
            tool_call={"name": name},
        )
    else:
        appointment = cancel_patient_appointment(
            arguments["appointment_id"], identity, db
        )
        result = _base(
            "Consulta cancelada com sucesso.",
            name,
            tool_result={"type": "appointment_cancelled", "appointment": appointment},
            tool_call={"name": name},
        )
    return {"result": result}


def _build_action_graph(checkpointer):
    builder = StateGraph(ActionGraphState)
    builder.add_node("confirm_action", confirm_action_node)
    builder.add_edge(START, "confirm_action")
    builder.add_edge("confirm_action", END)
    return builder.compile(checkpointer=checkpointer)


@lru_cache
def graph_app():
    return _build_graph(checkpointer())


@lru_cache
def action_graph_app():
    return _build_action_graph(checkpointer())


def _action_config(thread_id: str) -> dict:
    return {
        # A deterministic sub-thread prevents action checkpoints from replacing
        # the conversational checkpoint while remaining scoped to ChatSession.id.
        "configurable": {"thread_id": f"{thread_id}:actions"},
        "metadata": {"tenant": "redacted", "authenticated": True},
    }


def start_action_graph(
    db,
    tenant_id: str,
    identity: dict | None,
    tool_name: str,
    arguments: dict,
    thread_id: str,
    confirmation_id: str,
) -> dict:
    runtime_token = graph_runtime_context.set((db, tenant_id, identity))
    try:
        with tracing_context(enabled=False):
            output = action_graph_app().invoke(
                {
                    "tool_name": tool_name,
                    "tool_arguments": arguments,
                    "confirmation_id": confirmation_id,
                },
                _action_config(thread_id),
            )
        interruptions = output.get("__interrupt__", ())
        if interruptions:
            return _base(
                "Tudo certo. Revise os dados abaixo antes de concluir.",
                tool_name,
                confirmation_request=interruptions[0].value,
                tool_call={"name": tool_name},
            )
        return output["result"]
    finally:
        graph_runtime_context.reset(runtime_token)


def resume_action_graph(
    db,
    tenant_id: str,
    identity: dict | None,
    thread_id: str,
    confirmation_id: str,
    accepted: bool,
) -> dict:
    config = _action_config(thread_id)
    app = action_graph_app()
    snapshot = app.get_state(config)
    if (
        not snapshot.next
        or snapshot.values.get("confirmation_id") != confirmation_id
    ):
        raise ValueError("Confirmação expirada")
    runtime_token = graph_runtime_context.set((db, tenant_id, identity))
    try:
        with tracing_context(enabled=False):
            output = app.invoke(Command(resume=accepted), config)
        return output["result"]
    finally:
        graph_runtime_context.reset(runtime_token)


def run_graph(
    db,
    tenant_id: str,
    identity: dict | None,
    message: str,
    history: list[dict] | None,
    session_state: dict | None,
    thread_id: str,
) -> dict:
    legacy = dict(session_state or {})
    initial: GraphState = {
        "message": message,
        "history": history or [],
        "legacy_state": legacy,
        "result": {},
        "tool_name": "",
        "tool_arguments": {},
    }
    if legacy.get("dialog"):
        initial["dialog"] = dict(legacy["dialog"])
    runtime_token = graph_runtime_context.set((db, tenant_id, identity))
    try:
        # Authenticated conversations may contain appointment or identity data;
        # keep those runs local. Anonymous runs are redacted before tracing.
        tracing_enabled = get_settings().langsmith_tracing and not identity
        with tracing_context(enabled=tracing_enabled):
            output = graph_app().invoke(
                initial,
                {
                    "configurable": {"thread_id": thread_id},
                    "metadata": {"tenant": "redacted", "authenticated": bool(identity)},
                },
            )
        return output["result"]
    finally:
        graph_runtime_context.reset(runtime_token)


def consume_pending_tool(thread_id: str) -> dict | None:
    """Atomically make an authentication-paused tool unavailable for replay."""
    config = {"configurable": {"thread_id": thread_id}}
    app = graph_app()
    snapshot = app.get_state(config)
    result = dict(snapshot.values.get("result") or {})
    pending = result.pop("pending_tool", None)
    if pending:
        app.update_state(config, {"result": result})
    return pending
