from __future__ import annotations

from collections.abc import Callable

from app.agent.conversation import ConversationContext, ConversationTurn
from app.agent.routing import Domain, RouteDecision, RuleChain, Topic
from app.agent.routing.context import resolve_from_context
from app.agent.routing.rules import normalize
from app.agent.understanding.models import AnswerRequirement, TurnUnderstanding

SemanticInterpreter = Callable[[str, tuple[ConversationTurn, ...]], TurnUnderstanding | None]


class TurnInterpreter:
    """Hybrid interpretation: deterministic guardrails plus structured semantics.

    Security/clinical decisions can never be overridden by a model. For ordinary language, a
    structured provider may add obligations; the deterministic implementation remains a complete
    offline fallback and is exercised by the regression suite.
    """

    def __init__(
        self,
        rules: RuleChain,
        semantic_interpreter: SemanticInterpreter | None = None,
    ) -> None:
        self.rules = rules
        self.semantic_interpreter = semantic_interpreter

    def understand(
        self,
        message: str,
        context: ConversationContext,
        history: tuple[ConversationTurn, ...] = (),
    ) -> TurnUnderstanding:
        guarded_route = resolve_from_context(self.rules.classify(message), message, context)
        if guarded_route.domain in {Domain.SECURITY, Domain.CLINICAL_SAFETY}:
            return TurnUnderstanding(route=guarded_route)

        semantic = self._semantic(message, history)
        route = guarded_route
        if semantic is not None and semantic.route.confidence >= 0.7:
            route = semantic.route.model_copy(
                update={
                    "conversation_marker": guarded_route.conversation_marker
                    or semantic.route.conversation_marker
                }
            )
        requirements = list(
            dict.fromkeys(
                [
                    *self._deterministic_requirements(route, message),
                    *(semantic.requirements if semantic else []),
                ]
            )
        )
        text = normalize(message)
        return TurnUnderstanding(
            route=route,
            requirements=requirements,
            refers_to_previous_result=(
                bool(semantic and semantic.refers_to_previous_result)
                or _references_previous_result(text)
            ),
            correction=bool(semantic and semantic.correction) or _is_correction(text),
        )

    def _semantic(
        self, message: str, history: tuple[ConversationTurn, ...]
    ) -> TurnUnderstanding | None:
        if self.semantic_interpreter is None:
            return None
        try:
            return self.semantic_interpreter(message, history)
        except Exception:
            return None

    @staticmethod
    def _deterministic_requirements(route: RouteDecision, message: str) -> list[AnswerRequirement]:
        text = normalize(message)
        if route.topic == Topic.DOCTOR:
            requirements = [
                AnswerRequirement.SERVICE_CONFIRMATION,
                AnswerRequirement.PROFESSIONALS,
            ]
            if Topic.INSURER in route.secondary_topics or any(
                term in text for term in ("convenio", "convenios", "plano", "planos")
            ):
                requirements.append(AnswerRequirement.INSURERS)
            return requirements
        if route.topic == Topic.INSURER:
            return [AnswerRequirement.INSURERS]
        if route.topic == Topic.AVAILABILITY:
            return [AnswerRequirement.AVAILABILITY]
        if route.topic == Topic.OWN_APPOINTMENT:
            return [AnswerRequirement.APPOINTMENTS]
        if route.domain == Domain.KNOWLEDGE:
            return [AnswerRequirement.INSTITUTIONAL_GUIDANCE]
        return []


def _references_previous_result(text: str) -> bool:
    words = set(text.split())
    return bool(
        words & {"eles", "elas", "esse", "essa", "esses", "essas", "ali"}
    ) or text.startswith(("e ", "mas "))


def _is_correction(text: str) -> bool:
    return any(term in text for term in ("corrigindo", "falei errado", "dia errado", "na verdade"))
