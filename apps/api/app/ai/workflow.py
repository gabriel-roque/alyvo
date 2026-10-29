from __future__ import annotations

from typing import Literal, TypedDict

from sqlalchemy.orm import Session

from app.ai.providers import chat_provider
from app.ai.retrieval import retrieve


class ConversationState(TypedDict, total=False):
    tenant_id: str
    patient_id: str | None
    message: str
    intent: str
    requires_auth: bool
    route: str
    answer: str
    citations: list[dict]
    confidence: float
    form_request: dict
    confirmation_request: dict
    graph_trace: list[str]


def classify(message: str) -> str:
    lowered = message.casefold()
    if any(word in lowered for word in ("diagnóstico", "diagnostico", "dor no peito", "receita", "prescreva")):
        return "clinical_safety"
    if any(word in lowered for word in ("cancelar", "desmarcar")):
        return "cancel_appointment"
    if any(word in lowered for word in ("agendar", "horário", "horario", "consulta")):
        return "schedule"
    if any(word in lowered for word in ("humano", "recepção", "recepcao", "ticket")):
        return "ticket"
    return "knowledge"


def route_for(intent: str, authenticated: bool) -> Literal["safety", "auth", "schedule", "ticket", "retrieval"]:
    if intent == "clinical_safety":
        return "safety"
    if intent in {"schedule", "cancel_appointment"} and not authenticated:
        return "auth"
    if intent in {"schedule", "cancel_appointment"}:
        return "schedule"
    if intent == "ticket":
        return "ticket"
    return "retrieval"


def run_workflow(db: Session, initial: ConversationState) -> ConversationState:
    """LangGraph-equivalent state machine with deterministic, testable nodes.

    The optional compiled graph below documents the production topology; this runner
    keeps DB injection explicit and is used by HTTP handlers and unit tests.
    """
    state = dict(initial)
    trace = ["classify_intent"]
    state["intent"] = classify(state["message"])
    state["requires_auth"] = state["intent"] in {"schedule", "cancel_appointment"}
    state["route"] = route_for(state["intent"], bool(state.get("patient_id")))
    trace.append(f"route:{state['route']}")

    if state["route"] == "safety":
        state["answer"] = (
            "Posso ajudar apenas com informações administrativas. Não faço diagnóstico, prescrição ou triagem. "
            "Em uma emergência, procure o serviço de urgência da sua região."
        )
        state["citations"] = []
        state["confidence"] = 1.0
    elif state["route"] == "auth":
        state["answer"] = "Para proteger seus dados, confirme seu CPF e o código temporário antes de continuar."
        state["form_request"] = {"type": "patient_auth", "fields": ["cpf"]}
        state["citations"] = []
        state["confidence"] = 1.0
    elif state["route"] == "schedule":
        state["answer"] = "Encontrei horários reais na agenda. Escolha uma opção e confirme o resumo antes de agendar."
        state["form_request"] = {"type": "availability", "endpoint": "/availability"}
        state["citations"] = [{"title": "Agenda operacional", "source": "PostgreSQL", "excerpt": "Disponibilidade em tempo real"}]
        state["confidence"] = 1.0
    elif state["route"] == "ticket":
        state["answer"] = "Posso encaminhar sua dúvida para a recepção. Confirme a criação do ticket."
        state["confirmation_request"] = {"type": "ticket", "label": "Criar ticket"}
        state["citations"] = []
        state["confidence"] = 1.0
    else:
        result = retrieve(db, state["tenant_id"], state["message"])
        state["citations"] = result.citations
        state["confidence"] = result.confidence
        trace.append(f"retrieve:{result.strategy}")
        state["answer"] = chat_provider().complete(state["message"], result.answer_context)
        if result.confidence < 0.6:
            state["confirmation_request"] = {"type": "ticket", "label": "Falar com a recepção"}
    trace.append("compose_response")
    state["graph_trace"] = trace
    return state


def build_langgraph():
    """Compile the routing topology when LangGraph is installed."""
    from langgraph.graph import END, StateGraph

    graph = StateGraph(ConversationState)
    graph.add_node("classify", lambda state: {**state, "intent": classify(state["message"])})
    graph.add_node("route", lambda state: {**state, "route": route_for(state["intent"], bool(state.get("patient_id")))})
    graph.add_node("execute", lambda state: state)
    graph.set_entry_point("classify")
    graph.add_edge("classify", "route")
    graph.add_edge("route", "execute")
    graph.add_edge("execute", END)
    return graph.compile()

