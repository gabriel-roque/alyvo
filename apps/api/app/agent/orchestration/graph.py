from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph

from app.agent.conversation import ConversationContext, ConversationTurn
from app.agent.planning import DecisionPolicy, ExecutionPlan
from app.agent.presentation import (
    CompositionRequest,
    ResponseComposer,
    present_tool_result,
    response,
)
from app.agent.presentation.enrichment import post_appointment_guidance
from app.agent.routing import ConversationMarker, Domain, RouteDecision, RuleChain
from app.agent.routing.rules import normalize
from app.agent.tools import ToolGate, ToolInvocationPolicy, ToolRegistry, build_tool_registry
from app.agent.tools.models import AppointmentResult, ToolResult
from app.agent.understanding import AnswerRequirement, TurnInterpreter, TurnUnderstanding
from app.bootstrap.config import get_settings
from app.modules.identity.domain import Actor
from app.shared.infrastructure.observability import record


class AgentState(TypedDict, total=False):
    message: str
    normalized_message: str
    actor: Actor | None
    context: ConversationContext
    history: tuple[ConversationTurn, ...]
    route: RouteDecision
    understanding: TurnUnderstanding
    plan: ExecutionPlan
    tool_name: str
    tool_arguments: dict[str, object]
    tool_result: ToolResult
    result: dict[str, object]


@dataclass(frozen=True)
class AgentOutcome:
    response: dict[str, object]
    context: ConversationContext
    route: RouteDecision
    plan: ExecutionPlan


class AgentOrchestrator:
    def __init__(
        self,
        rules: RuleChain | None = None,
        tools: ToolRegistry | None = None,
        policy: DecisionPolicy | None = None,
        composer: ResponseComposer | None = None,
    ):
        if rules is None:
            from app.infrastructure.llm import turn_interpreter

            rules = RuleChain()
            semantic_interpreter = turn_interpreter()
        else:
            semantic_interpreter = None
        self.rules = rules
        self.interpreter = TurnInterpreter(rules, semantic_interpreter)
        self.tools = tools or build_tool_registry()
        self.policy = policy or DecisionPolicy()
        if composer is None:
            from app.infrastructure.llm import response_composer

            composer = response_composer()
        self.composer = composer
        self.tool_policy = ToolInvocationPolicy()
        self.graph = self._build_graph()

    def run(
        self,
        message: str,
        actor: Actor | None = None,
        context: ConversationContext | None = None,
        history: tuple[ConversationTurn, ...] = (),
    ) -> dict[str, object]:
        return self.run_with_context(message, actor, context, history).response

    def run_with_context(
        self,
        message: str,
        actor: Actor | None = None,
        context: ConversationContext | None = None,
        history: tuple[ConversationTurn, ...] = (),
    ) -> AgentOutcome:
        started = time.perf_counter()
        initial_context = (context or ConversationContext()).next_turn()
        output = self.graph.invoke(
            {
                "message": message,
                "actor": actor,
                "context": initial_context,
                "history": history[-6:],
            }
        )
        outcome = AgentOutcome(
            response=output["result"],
            context=output["context"],
            route=output["route"],
            plan=output["plan"],
        )
        understanding = output["understanding"]
        record(
            "agent.decision",
            route_source=outcome.route.source,
            domain=outcome.route.domain,
            action=outcome.route.action,
            topic=outcome.route.topic,
            confidence=outcome.route.confidence,
            plan_kind=outcome.plan.kind,
            tools=[step.tool_name for step in outcome.plan.steps],
            answer_requirements=list(understanding.requirements),
            refers_to_previous_result=understanding.refers_to_previous_result,
            correction=understanding.correction,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return outcome

    @staticmethod
    def _normalize(state: AgentState) -> dict[str, object]:
        return {"normalized_message": normalize(state["message"])}

    def _understand(self, state: AgentState) -> dict[str, object]:
        understanding = self.interpreter.understand(
            state["message"], state["context"], state.get("history", ())
        )
        return {"understanding": understanding, "route": understanding.route}

    def _plan(self, state: AgentState) -> dict[str, object]:
        settings = get_settings()
        today = datetime.now(ZoneInfo(settings.clinic_timezone)).date()
        plan = self.policy.plan(state["route"], state["message"], state["context"], today)
        update: dict[str, object] = {"plan": plan, "context": plan.context}
        if plan.response is not None:
            update["result"] = plan.response
            return update
        step = plan.first_step
        if step is None:
            raise RuntimeError("Plano executável sem etapa")
        update["tool_name"] = step.tool_name
        update["tool_arguments"] = step.arguments
        return update

    def _execute(self, state: AgentState) -> dict[str, object]:
        if state.get("result"):
            return {}
        actor = state.get("actor")
        executed: list[ToolResult] = []
        for step in state["plan"].steps:
            spec = self.tools.get(step.tool_name)
            gate = self.tool_policy.evaluate(spec, actor)
            if gate == ToolGate.AUTHENTICATE:
                return {
                    "result": response(
                        "Confirme sua identidade para continuar.",
                        spec.name,
                        auth_required=True,
                        pending_tool={"name": spec.name, "arguments": step.arguments},
                    )
                }
            if gate == ToolGate.CONFIRM:
                return {
                    "result": response(
                        "Revise os dados antes de concluir esta operação.",
                        spec.name,
                        pending_tool={"name": spec.name, "arguments": step.arguments},
                    )
                }
            arguments = spec.handler.arguments_model.model_validate(step.arguments)
            executed.append(spec.handler.execute(arguments, actor))
        if not executed:
            raise RuntimeError("Plano executável sem resultado")
        result = executed[0]
        update: dict[str, object] = {"tool_result": result}
        if result.type == "directory":
            update["context"] = state["context"].with_directory_result(
                state["message"],
                [item.id for item in result.items],
                [item.specialty for item in result.items],
            )
        return update

    @staticmethod
    def _validate(state: AgentState) -> dict[str, object]:
        if state.get("result"):
            return {}
        state["tool_result"].model_dump(mode="json")
        requirements = state["understanding"].requirements
        if (
            AnswerRequirement.INSURERS in requirements
            and state["tool_result"].type == "directory"
            and any(item.insurers is None for item in state["tool_result"].items)
        ):
            raise RuntimeError("Plano incompleto: convênios não foram resolvidos")
        return {}

    def _present_node(self, state: AgentState) -> dict[str, object]:
        draft = state.get("result")
        tool_result = state.get("tool_result")
        if draft is None:
            if tool_result is None:
                raise RuntimeError("Apresentação sem resposta ou resultado de ferramenta")
            draft = present_tool_result(
                state["tool_name"],
                tool_result,
                tuple(state["understanding"].requirements),
            )
        draft = _apply_conversation_marker(draft, state["route"], state["message"])
        result = self.composer.compose(
            CompositionRequest(
                message=state["message"],
                history=state.get("history", ()),
                domain=state["route"].domain,
                action=state["route"].action,
                topic=state["route"].topic,
                plan_kind=state["plan"].kind,
                draft=draft,
                tool_result=tool_result.model_dump(mode="json") if tool_result else None,
            )
        )
        return {"result": result}

    def _build_graph(self) -> Any:
        graph = StateGraph(AgentState)
        graph.add_node("normalize", self._normalize)
        graph.add_node("understand", self._understand)
        graph.add_node("plan", self._plan)
        graph.add_node("execute", self._execute)
        graph.add_node("validate", self._validate)
        graph.add_node("present", self._present_node)
        graph.add_edge(START, "normalize")
        graph.add_edge("normalize", "understand")
        graph.add_edge("understand", "plan")
        graph.add_edge("plan", "execute")
        graph.add_edge("execute", "validate")
        graph.add_edge("validate", "present")
        graph.add_edge("present", END)
        return graph.compile()

    def present_result(self, tool_name: str, result: ToolResult) -> dict[str, object]:
        draft = present_tool_result(tool_name, result)
        if isinstance(result, AppointmentResult) and result.type in {
            "appointment_created",
            "appointment_rescheduled",
        }:
            guidance, citations = post_appointment_guidance(result)
            if guidance:
                draft = {
                    **draft,
                    "answer": str(draft["answer"]) + guidance,
                    "citations": citations,
                }
        scheduling = tool_name in {
            "search_availability",
            "list_my_appointments",
            "create_appointment",
            "cancel_appointment",
            "start_reschedule",
            "reschedule_appointment",
        }
        return self.composer.compose(
            CompositionRequest(
                message="Apresente de forma natural o resultado solicitado pelo paciente.",
                history=(),
                domain="scheduling" if scheduling else "directory",
                action="execute",
                topic=tool_name,
                plan_kind="tool",
                draft=draft,
                tool_result=result.model_dump(mode="json"),
            )
        )


def _apply_conversation_marker(
    result: dict[str, object], route: RouteDecision, message: str
) -> dict[str, object]:
    marker = route.conversation_marker
    if marker is None or route.domain == Domain.CONVERSATION:
        return result
    prefixes = {
        ConversationMarker.GREETING: _greeting_prefix(message),
        ConversationMarker.THANKS: "Por nada! ",
        ConversationMarker.FAREWELL: "Claro, antes de você ir: ",
    }
    answer = str(result["answer"])
    return {**result, "answer": prefixes[marker] + answer}


def _greeting_prefix(message: str) -> str:
    text = normalize(message)
    if "bom dia" in text:
        return "Bom dia! "
    if "boa tarde" in text:
        return "Boa tarde! "
    if "boa noite" in text:
        return "Boa noite! "
    return "Oi! "
