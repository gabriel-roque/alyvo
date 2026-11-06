from __future__ import annotations

from datetime import date, timedelta
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.presentation import present_tool_result, response
from app.agent.routing import Action, Domain, RouteDecision, RuleChain, Topic
from app.agent.tools import ToolRegistry, build_tool_registry
from app.agent.tools.models import ToolResult
from app.modules.identity.domain import Actor


class AgentState(TypedDict, total=False):
    message: str
    normalized_message: str
    actor: Actor | None
    route: RouteDecision
    tool_name: str
    tool_arguments: dict
    tool_result: ToolResult
    result: dict


class AgentOrchestrator:
    def __init__(self, rules: RuleChain | None = None, tools: ToolRegistry | None = None):
        if rules is None:
            from app.infrastructure.providers import routing_classifier

            rules = RuleChain(fallback_classifier=routing_classifier())
        self.rules = rules
        self.tools = tools or build_tool_registry()
        self.graph = self._build_graph()

    def run(self, message: str, actor: Actor | None = None) -> dict:
        output = self.graph.invoke({"message": message, "actor": actor})
        return output["result"]

    @staticmethod
    def _normalize(state: AgentState) -> dict:
        from app.agent.routing.rules import normalize

        return {"normalized_message": normalize(state["message"])}

    def _classify(self, state: AgentState) -> dict:
        return {"route": self.rules.classify(state["normalized_message"])}

    def _plan(self, state: AgentState) -> dict:
        route = state["route"]
        immediate = self._immediate(route)
        if immediate:
            return {"result": immediate}
        name, arguments = self._tool_call(route, state["message"])
        return {"tool_name": name, "tool_arguments": arguments}

    def _execute(self, state: AgentState) -> dict:
        if state.get("result"):
            return {}
        spec = self.tools.get(state["tool_name"])
        actor = state.get("actor")
        if spec.requires_authentication and actor is None:
            return {
                "result": response(
                    "Confirme sua identidade para continuar.",
                    spec.name,
                    auth_required=True,
                    pending_tool={"name": spec.name, "arguments": state["tool_arguments"]},
                )
            }
        arguments = spec.handler.arguments_model.model_validate(state["tool_arguments"])
        return {"tool_result": spec.handler.execute(arguments, actor)}

    @staticmethod
    def _validate(state: AgentState) -> dict:
        if state.get("result"):
            return {}
        state["tool_result"].model_dump(mode="json")
        return {}

    @staticmethod
    def _present_node(state: AgentState) -> dict:
        if state.get("result"):
            return {}
        return {"result": present_tool_result(state["tool_name"], state["tool_result"])}

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("normalize", self._normalize)
        graph.add_node("classify", self._classify)
        graph.add_node("plan", self._plan)
        graph.add_node("execute", self._execute)
        graph.add_node("validate", self._validate)
        graph.add_node("present", self._present_node)
        graph.add_edge(START, "normalize")
        graph.add_edge("normalize", "classify")
        graph.add_edge("classify", "plan")
        graph.add_edge("plan", "execute")
        graph.add_edge("execute", "validate")
        graph.add_edge("validate", "present")
        graph.add_edge("present", END)
        return graph.compile()

    @staticmethod
    def _immediate(route: RouteDecision) -> dict | None:
        if route.domain == Domain.CLINICAL_SAFETY:
            return response(
                "Não realizo diagnóstico ou triagem. Em caso de risco imediato, procure um serviço de emergência.",
                "clinical_safety",
                confidence=1,
            )
        if route.domain == Domain.SECURITY:
            return response(
                "Não posso revelar dados de outra pessoa ou ignorar regras de segurança.",
                "security",
            )
        messages = {
            Action.GREET: "Olá! Como posso ajudar você hoje?",
            Action.THANK: "Por nada! Posso ajudar com agenda e informações da clínica.",
            Action.FAREWELL: "Até logo!",
            Action.DESCRIBE: "Posso informar médicos, convênios, exames, unidades e horários, além de ajudar com suas consultas.",
        }
        return (
            response(messages[route.action], "conversation") if route.action in messages else None
        )

    @staticmethod
    def _tool_call(route: RouteDecision, message: str) -> tuple[str, dict]:
        if route.topic == Topic.INSURER:
            return "list_insurers", {}
        if route.topic == Topic.SPECIALTY:
            return "list_specialties", {}
        if route.topic == Topic.UNIT:
            return "list_units", {}
        if route.topic == Topic.EXAM:
            return "list_exams", {}
        if route.topic == Topic.DOCTOR:
            return "search_directory", {"query": ""}
        if route.topic == Topic.OWN_APPOINTMENT:
            return "list_my_appointments", {}
        if route.topic == Topic.AVAILABILITY:
            today = date.today()
            return "search_availability", {
                "from_date": today.isoformat(),
                "to_date": (today + timedelta(days=14)).isoformat(),
            }
        return "search_knowledge", {"query": message}
