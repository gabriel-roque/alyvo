from __future__ import annotations

from datetime import date

from app.agent.conversation import ConversationContext
from app.agent.planning.capabilities import CapabilityRegistry
from app.agent.planning.models import ExecutionPlan, PlanKind, PlanStep
from app.agent.planning.scheduling import (
    build_appointment_selection_plan,
    build_availability_plan,
)
from app.agent.presentation import response
from app.agent.routing import Action, Domain, RiskLevel, RouteDecision, Topic
from app.agent.routing.rules import normalize


class DecisionPolicy:
    """Turns an interpretation into an auditable, deterministic execution plan."""

    def __init__(self, capabilities: CapabilityRegistry | None = None) -> None:
        self.capabilities = capabilities or CapabilityRegistry()

    def plan(
        self,
        route: RouteDecision,
        message: str,
        context: ConversationContext,
        today: date,
    ) -> ExecutionPlan:
        direct = self._direct_response(route, message)
        if direct is not None:
            keep_context = (
                route.domain == Domain.CONVERSATION and route.reason != "declined pending question"
            )
            next_context = context if keep_context else context.clear_topic()
            return ExecutionPlan(
                kind=self._direct_kind(route),
                response=direct,
                reason_codes=[f"direct:{route.domain}:{route.action}"],
                context=next_context,
            )
        if route.topic == Topic.AVAILABILITY and route.action == Action.CREATE:
            return build_appointment_selection_plan(message, context)
        if route.topic == Topic.AVAILABILITY:
            return build_availability_plan(message, context, today)
        return self._tool_or_rag_plan(route, message, context)

    def _tool_or_rag_plan(
        self, route: RouteDecision, message: str, context: ConversationContext
    ) -> ExecutionPlan:
        capability = self.capabilities.resolve(route.domain, route.action, route.topic)
        tool_name = capability.tool_name if capability else "search_knowledge"
        arguments: dict[str, object] = {}
        if tool_name == "search_directory":
            arguments = {"query": message}
            if route.source.value == "context" and context.directory.doctor_ids:
                arguments["doctor_ids"] = context.directory.doctor_ids
        elif tool_name == "search_knowledge":
            arguments = {"query": message}
        kind = PlanKind.RAG if tool_name == "search_knowledge" else PlanKind.TOOL
        reason = "approved_documents" if kind == PlanKind.RAG else "authoritative_structured_data"
        return ExecutionPlan(
            kind=kind,
            steps=[PlanStep(tool_name=tool_name, arguments=arguments)],
            reason_codes=[reason],
            context=context.clear_topic().with_tool(tool_name),
        )

    @staticmethod
    def _direct_kind(route: RouteDecision) -> PlanKind:
        if route.domain in {Domain.SECURITY, Domain.CLINICAL_SAFETY}:
            return PlanKind.REJECT
        if route.domain == Domain.FALLBACK:
            return PlanKind.CLARIFICATION
        return PlanKind.DIRECT

    @staticmethod
    def _direct_response(route: RouteDecision, message: str) -> dict[str, object] | None:
        if route.domain == Domain.CLINICAL_SAFETY:
            return _clinical_response(route)
        if route.domain == Domain.SECURITY:
            return response(
                "Não posso revelar dados de outra pessoa ou ignorar regras de segurança.",
                "security",
            )
        if route.domain == Domain.FALLBACK:
            return _clarification_response(route)
        messages = {
            Action.GREET: _greeting(message),
            Action.THANK: "Imagina! Se precisar de mais alguma coisa, estou por aqui.",
            Action.FAREWELL: "Até logo! Espero ter ajudado. Cuide-se!",
            Action.DESCRIBE: (
                "Posso ajudar a encontrar médicos, consultar convênios, exames e unidades, "
                "verificar horários e acompanhar suas consultas. Por onde você prefere começar?"
            ),
        }
        answer = messages.get(route.action)
        return response(answer, "conversation") if answer else None


def _clinical_response(route: RouteDecision) -> dict[str, object]:
    if route.risk == RiskLevel.URGENT:
        answer = (
            "Sinto muito que você esteja passando por isso. Esses sinais podem precisar de "
            "atendimento imediato. Procure um pronto atendimento ou ligue para o serviço de "
            "emergência da sua região."
        )
    else:
        answer = (
            "Sinto muito que você não esteja bem. Para sua segurança, não consigo indicar uma "
            "especialidade apenas pelos sintomas. O ideal é conversar com um profissional de "
            "saúde; se a dor for súbita, muito intensa ou vier com outros sinais preocupantes, "
            "procure atendimento de urgência."
        )
    return response(answer, "clinical_safety", confidence=1)


def _clarification_response(route: RouteDecision) -> dict[str, object]:
    negated = route.reason == "negated operation"
    answer = (
        "Entendi que você não quer realizar essa operação. Em que posso ajudar?"
        if negated
        else "Quero entender direitinho para ajudar. Você procura informações da clínica, um médico ou um horário para consulta?"
    )
    return response(
        answer,
        "clarify",
        suggestions=[
            {"label": "Informações da clínica", "message": "Quero informações da clínica"},
            {"label": "Encontrar um médico", "message": "Quero encontrar um médico"},
            {"label": "Ver horários", "message": "Quero ver horários disponíveis"},
        ],
    )


def _greeting(message: str) -> str:
    text = normalize(message)
    social = " Estou bem, obrigada por perguntar." if "tudo bem" in text else ""
    if "bom dia" in text:
        return f"Bom dia!{social} Como posso ajudar você hoje?"
    if "boa tarde" in text:
        return f"Boa tarde!{social} Como posso ajudar você?"
    if "boa noite" in text:
        return f"Boa noite!{social} Como posso ajudar você?"
    return f"Oi!{social or ' Que bom falar com você.'} Como posso ajudar hoje?"
