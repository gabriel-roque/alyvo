from __future__ import annotations

from datetime import date

from app.agent.conversation import AvailabilitySlots, ConversationContext
from app.agent.orchestration.dates import extract_availability_slots
from app.agent.planning.models import ExecutionPlan, PlanKind, PlanStep
from app.agent.presentation import response
from app.agent.routing import Action, Domain, RiskLevel, RouteDecision, Topic
from app.agent.routing.rules import normalize


class DecisionPolicy:
    """Turns an interpretation into an auditable, deterministic execution plan."""

    def plan(
        self,
        route: RouteDecision,
        message: str,
        context: ConversationContext,
        today: date,
    ) -> ExecutionPlan:
        direct = self._direct_response(route, message)
        if direct is not None:
            next_context = context if route.domain == Domain.CONVERSATION else context.clear_topic()
            return ExecutionPlan(
                kind=self._direct_kind(route),
                response=direct,
                reason_codes=[f"direct:{route.domain}:{route.action}"],
                context=next_context,
            )
        if route.topic == Topic.AVAILABILITY:
            return self._availability_plan(message, context, today)
        return self._tool_or_rag_plan(route, message, context)

    @staticmethod
    def _availability_plan(
        message: str, context: ConversationContext, today: date
    ) -> ExecutionPlan:
        text = normalize(message)
        if any(term in text for term in ("outro dia", "outra data")):
            context = context.model_copy(update={"availability": AvailabilitySlots()})
        updated = context.with_availability(extract_availability_slots(message, today))
        if updated.availability.from_date is None:
            return ExecutionPlan(
                kind=PlanKind.CLARIFICATION,
                response=response(
                    "Claro! Para qual dia você gostaria de consultar os horários?",
                    "clarify_availability",
                    suggestions=[
                        {"label": "Amanhã", "message": "Quero horários para amanhã"},
                        {
                            "label": "Próxima sexta-feira",
                            "message": "Quero horários na próxima sexta-feira",
                        },
                    ],
                ),
                reason_codes=["missing_slot:availability.date"],
                context=updated,
            )
        return ExecutionPlan(
            kind=PlanKind.TOOL,
            steps=[
                PlanStep(
                    tool_name="search_availability",
                    arguments=updated.availability.tool_arguments(),
                )
            ],
            reason_codes=["authoritative_data:scheduling"],
            context=updated.with_tool("search_availability"),
        )

    @staticmethod
    def _tool_or_rag_plan(
        route: RouteDecision, message: str, context: ConversationContext
    ) -> ExecutionPlan:
        tool_name, arguments = _tool_call(route, message)
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


def _tool_call(route: RouteDecision, message: str) -> tuple[str, dict[str, object]]:
    topic_tools = {
        Topic.INSURER: "list_insurers",
        Topic.SPECIALTY: "list_specialties",
        Topic.UNIT: "list_units",
        Topic.EXAM: "list_exams",
        Topic.DOCTOR: "search_directory",
    }
    if route.topic == Topic.OWN_APPOINTMENT:
        return "list_my_appointments", {}
    if route.topic in topic_tools:
        arguments: dict[str, object] = {"query": message} if route.topic == Topic.DOCTOR else {}
        return topic_tools[route.topic], arguments
    return "search_knowledge", {"query": message}


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
