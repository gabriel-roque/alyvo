from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.agent.conversation import ConversationTurn
from app.agent.presentation.prompts import system_prompt, user_prompt

JsonObject = dict[str, object]


class AnswerGenerator(Protocol):
    def generate(self, system: str, prompt: str) -> str | None: ...


@dataclass(frozen=True)
class CompositionRequest:
    message: str
    history: tuple[ConversationTurn, ...]
    domain: str
    action: str
    topic: str
    plan_kind: str
    draft: JsonObject
    tool_result: JsonObject | None = None


class ResponseComposer(Protocol):
    def compose(self, request: CompositionRequest) -> JsonObject: ...


class DeterministicResponseComposer:
    def compose(self, request: CompositionRequest) -> JsonObject:
        return request.draft


class LlmResponseComposer:
    """Lets the LLM phrase an answer without delegating execution authority to it."""

    _LOCKED_DOMAINS = {"security", "clinical_safety"}
    _FORBIDDEN_OUTPUT = ("fontes consultadas", "tool_result", "```json", "system prompt")

    def __init__(
        self,
        generator: AnswerGenerator,
        clinic_name: str,
        fallback: ResponseComposer | None = None,
    ) -> None:
        self._generator = generator
        self._clinic_name = clinic_name
        self._fallback = fallback or DeterministicResponseComposer()

    def compose(self, request: CompositionRequest) -> JsonObject:
        fallback = self._fallback.compose(request)
        if request.domain in self._LOCKED_DOMAINS:
            return fallback
        raw_citations = fallback.get("citations", [])
        citations = raw_citations if isinstance(raw_citations, list) else []
        prompt = user_prompt(
            message=request.message,
            history=request.history,
            decision={
                "domain": request.domain,
                "action": request.action,
                "topic": request.topic,
                "plan_kind": request.plan_kind,
            },
            safe_draft=str(fallback["answer"]),
            authoritative_data=request.tool_result,
            citations=citations,
        )
        answer = self._generator.generate(system_prompt(self._clinic_name), prompt)
        if not self._valid(answer):
            return fallback
        assert answer is not None
        return {**fallback, "answer": answer.strip()}

    def _valid(self, answer: str | None) -> bool:
        if not answer or len(answer.strip()) > 2_000:
            return False
        normalized = answer.casefold()
        return not any(term in normalized for term in self._FORBIDDEN_OUTPUT)
