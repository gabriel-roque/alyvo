from __future__ import annotations

from datetime import datetime
from typing import TypedDict
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph

from app.agent.orchestration.dates import parse_availability_request
from app.agent.presentation import present_tool_result, response
from app.agent.routing import Action, Domain, RiskLevel, RouteDecision, RuleChain, Topic
from app.agent.routing.rules import normalize
from app.agent.tools import ToolRegistry, build_tool_registry
from app.agent.tools.models import ToolResult
from app.bootstrap.config import get_settings
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
        immediate = self._immediate(route, state["message"])
        if immediate:
            return {"result": immediate}
        if route.topic == Topic.AVAILABILITY:
            arguments = self._availability_arguments(state["message"])
            if arguments is None:
                return {
                    "result": response(
                        "Claro! Para qual dia você gostaria de consultar os horários?",
                        "clarify_availability",
                        suggestions=[
                            {"label": "Amanhã", "message": "Quero horários para amanhã"},
                            {
                                "label": "Próxima sexta-feira",
                                "message": "Quero horários na próxima sexta-feira",
                            },
                        ],
                    )
                }
            return {"tool_name": "search_availability", "tool_arguments": arguments}
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
    def _immediate(route: RouteDecision, message: str) -> dict | None:
        if route.domain == Domain.CLINICAL_SAFETY:
            if route.risk == RiskLevel.URGENT:
                return response(
                    "Sinto muito que você esteja passando por isso. Esses sinais podem precisar de atendimento imediato. Procure um pronto atendimento ou ligue para o serviço de emergência da sua região.",
                    "clinical_safety",
                    confidence=1,
                )
            return response(
                "Sinto muito que você não esteja bem. Para sua segurança, não consigo indicar uma especialidade apenas pelos sintomas. O ideal é conversar com um profissional de saúde; se a dor for súbita, muito intensa ou vier com outros sinais preocupantes, procure atendimento de urgência.",
                "clinical_safety",
                confidence=1,
            )
        if route.domain == Domain.SECURITY:
            return response(
                "Não posso revelar dados de outra pessoa ou ignorar regras de segurança.",
                "security",
            )
        if route.domain == Domain.FALLBACK:
            return response(
                "Quero entender direitinho para ajudar. Você procura informações da clínica, um médico ou um horário para consulta?",
                "clarify",
                suggestions=[
                    {"label": "Informações da clínica", "message": "Quero informações da clínica"},
                    {"label": "Encontrar um médico", "message": "Quero encontrar um médico"},
                    {"label": "Ver horários", "message": "Quero ver horários disponíveis"},
                ],
            )
        greeting = AgentOrchestrator._greeting(message)
        messages = {
            Action.GREET: greeting,
            Action.THANK: "Imagina! Se precisar de mais alguma coisa, estou por aqui.",
            Action.FAREWELL: "Até logo! Espero ter ajudado. Cuide-se!",
            Action.DESCRIBE: "Posso ajudar a encontrar médicos, consultar convênios, exames e unidades, verificar horários e acompanhar suas consultas. Por onde você prefere começar?",
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
            return "search_directory", {"query": message}
        if route.topic == Topic.OWN_APPOINTMENT:
            return "list_my_appointments", {}
        return "search_knowledge", {"query": message}

    @staticmethod
    def _availability_arguments(message: str) -> dict | None:
        settings = get_settings()
        today = datetime.now(ZoneInfo(settings.clinic_timezone)).date()
        return parse_availability_request(message, today)

    @staticmethod
    def _greeting(message: str) -> str:
        text = normalize(message)
        if "bom dia" in text:
            return "Bom dia! Que bom ter você por aqui. Como posso ajudar?"
        if "boa tarde" in text:
            return "Boa tarde! Como posso ajudar você?"
        if "boa noite" in text:
            return "Boa noite! Como posso ajudar você?"
        return "Oi! Tudo bem? Como posso ajudar você hoje?"

    @staticmethod
    def _present(tool_name: str, result: ToolResult) -> dict:
        return present_tool_result(tool_name, result)
