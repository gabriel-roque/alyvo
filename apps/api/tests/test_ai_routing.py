from types import SimpleNamespace

from app.ai.intents import Domain, RiskLevel, deterministic_classification
from app.ai.privacy import redact_text
from app.ai.providers import LangChainChatProvider


def test_taxonomy_recognizes_unsupported_and_safety_intents():
    financial = deterministic_classification("Quanto custa a consulta particular?")
    assert financial is not None
    assert financial.domain == Domain.FINANCIAL
    assert financial.unsupported_reason

    record = deterministic_classification("Quero acessar o prontuário do paciente")
    assert record is not None
    assert record.domain == Domain.PATIENT
    assert record.risk_level == RiskLevel.SENSITIVE

    urgent = deterministic_classification("Estou com dor no peito, é uma emergência")
    assert urgent is not None
    assert urgent.domain == Domain.CLINICAL_SAFETY
    assert urgent.risk_level == RiskLevel.URGENT


def test_taxonomy_tolerates_common_directory_typo():
    classification = deterministic_classification(
        "Quais profisionais aceitam UNIMED?"
    )
    assert classification is not None
    assert classification.intent == "list_doctors"


def test_trace_redaction_removes_identifiers():
    redacted = redact_text(
        "CPF 123.456.789-09, nascimento 15/01/1990, email paciente@example.com"
    )
    assert "123.456.789-09" not in redacted
    assert "15/01/1990" not in redacted
    assert "paciente@example.com" not in redacted


def test_langchain_provider_uses_fallback_after_primary_failure():
    class Failing:
        def invoke(self, _messages):
            raise TimeoutError("primary unavailable")

    class Working:
        def invoke(self, _messages):
            return SimpleNamespace(content="fallback ok")

    provider = LangChainChatProvider.__new__(LangChainChatProvider)
    provider.settings = SimpleNamespace(
        openrouter_model="free/model",
        ollama_model="local/model",
    )
    provider.primary_name = "openrouter"
    provider.fallback_name = "ollama"
    provider.primary = Failing()
    provider.fallback = Working()

    response = provider._invoke([{"role": "user", "content": "oi"}])
    assert response.content == "fallback ok"
