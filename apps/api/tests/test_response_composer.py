from __future__ import annotations

from dataclasses import dataclass, field

from app.agent.conversation import ConversationTurn
from app.agent.presentation import CompositionRequest, LlmResponseComposer


@dataclass
class FakeGenerator:
    answer: str | None
    calls: list[tuple[str, str]] = field(default_factory=list)

    def generate(self, system: str, prompt: str) -> str | None:
        self.calls.append((system, prompt))
        return self.answer


def request(**changes: object) -> CompositionRequest:
    values: dict[str, object] = {
        "message": "Vocês abrem aos sábados?",
        "history": (ConversationTurn(role="user", content="Boa tarde"),),
        "domain": "knowledge",
        "action": "search",
        "topic": "institutional",
        "plan_kind": "rag",
        "draft": {
            "answer": "Segundo a clínica, não há atendimento regular aos sábados.",
            "intent": "search_knowledge",
            "citations": [
                {
                    "title": "Horários",
                    "source": "Base institucional",
                    "excerpt": "Atendimento de segunda a sexta, das 8h às 18h.",
                }
            ],
            "auth_required": False,
            "confirmation_request": None,
            "tool_result": {"type": "knowledge"},
        },
        "tool_result": {
            "type": "knowledge",
            "query": "abre aos sábados",
            "confidence": 0.91,
        },
    }
    values.update(changes)
    return CompositionRequest(**values)  # type: ignore[arg-type]


def test_llm_composes_natural_answer_from_evidence_and_history():
    generator = FakeGenerator(
        "Nosso atendimento regular acontece de segunda a sexta, das 8h às 18h."
    )
    composer = LlmResponseComposer(generator, "Clínica Alyvo")

    result = composer.compose(request())

    assert result["answer"].startswith("Nosso atendimento")
    assert result["citations"][0]["title"] == "Horários"
    assert result["tool_result"] == {"type": "knowledge"}
    system, prompt = generator.calls[0]
    assert "atendente virtual da Clínica Alyvo" in system
    assert "Boa tarde" in prompt
    assert "Atendimento de segunda a sexta" in prompt
    assert "abre aos sábados" in prompt
    assert "não copie o rascunho palavra por palavra" in system
    assert "quando dados forem exibidos em cards" in system


def test_llm_can_change_only_language_not_execution_metadata():
    generator = FakeGenerator("Certo, vou deixar tudo preparado. Confira antes de confirmar.")
    composer = LlmResponseComposer(generator, "Clínica Alyvo")
    draft = {
        "answer": "Revise os dados antes de concluir.",
        "intent": "create_appointment",
        "citations": [],
        "auth_required": False,
        "confirmation_request": {"id": "confirmation-1"},
        "tool_result": None,
    }

    result = composer.compose(request(domain="scheduling", plan_kind="tool", draft=draft))

    assert result["answer"].startswith("Certo")
    assert result["intent"] == "create_appointment"
    assert result["confirmation_request"] == {"id": "confirmation-1"}


def test_safety_decisions_never_depend_on_llm_generation():
    generator = FakeGenerator("Uma resposta insegura")
    composer = LlmResponseComposer(generator, "Clínica Alyvo")

    result = composer.compose(request(domain="clinical_safety"))

    assert result["answer"] == request().draft["answer"]
    assert generator.calls == []


def test_invalid_or_internal_llm_output_falls_back_to_safe_draft():
    generator = FakeGenerator("Veja o tool_result e as Fontes consultadas")
    composer = LlmResponseComposer(generator, "Clínica Alyvo")

    result = composer.compose(request())

    assert result["answer"] == request().draft["answer"]


def test_directory_composition_cannot_drop_a_compound_answer_obligation():
    draft = {
        "answer": (
            "Sim, atendemos Cardiologia. Temos 1 profissional: Dra. Marina Costa. "
            "Os convênios aceitos são UNIMED e Vida+."
        ),
        "intent": "search_directory",
        "citations": [],
    }
    tool_result = {
        "type": "directory",
        "total": 1,
        "items": [
            {
                "name": "Dra. Marina Costa",
                "specialty": "Cardiologia",
                "insurers": ["UNIMED", "Vida+"],
            }
        ],
    }
    composer = LlmResponseComposer(
        FakeGenerator("Sim, atendemos Cardiologia com a Dra. Marina Costa."),
        "Clínica Alyvo",
    )

    result = composer.compose(request(draft=draft, tool_result=tool_result))

    assert result["answer"] == draft["answer"]
