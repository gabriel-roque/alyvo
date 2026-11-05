import json
from pathlib import Path
from types import SimpleNamespace

from app.ai.intents import Domain, RiskLevel, deterministic_classification
from app.ai.privacy import redact_text
from app.ai.providers import LangChainChatProvider
from app.ai.tracing import (
    retrieval_span_inputs,
    retrieval_span_outputs,
    tool_span_inputs,
    tool_span_outputs,
)


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


def test_child_span_processors_do_not_export_sensitive_values():
    inputs = tool_span_inputs(
        {
            "db": object(),
            "tenant_id": "real-tenant-123",
            "identity": {"sub": "patient-456", "cpf": "123.456.789-09"},
            "name": "search_knowledge",
            "arguments": {
                "query": "segredo do paciente",
                "token": "super-secret-token",
            },
        }
    )
    assert inputs == {
        "tool_name": "search_knowledge",
        "argument_keys": ["query"],
        "unknown_argument_count": 1,
        "authenticated": True,
    }

    output = tool_span_outputs(
        {
            "answer": "conteúdo confidencial",
            "intent": "search_knowledge",
            "confidence": 0.9,
            "citations": [{"excerpt": "documento privado"}],
            "tool_result": {"type": "documents", "items": [{"body": "privado"}]},
        }
    )
    assert output["result_count"] == 1
    assert "conteúdo confidencial" not in repr(output)
    assert "documento privado" not in repr(output)

    retrieval_input = retrieval_span_inputs(
        {"tenant_id": "real-tenant-123", "question": "CPF 123.456.789-09"}
    )
    assert retrieval_input == {
        "query_present": True,
        "query_length_bucket": "1-32",
    }
    assert "123.456.789-09" not in repr(retrieval_input)
    assert retrieval_span_outputs(["raw document body"]) == {
        "status": "ok",
        "result_count": 1,
    }


def test_langgraph_config_discovers_local_demo_graph():
    root = Path(__file__).resolve().parents[3]
    config = json.loads((root / "langgraph.json").read_text())
    assert config["graphs"] == {
        "alyvo-local-demo": "./apps/api/app/ai/studio.py:studio_graph"
    }
    assert config["dependencies"] == ["."]


def test_studio_proxy_is_loopback_only_and_allows_langsmith_pna():
    root = Path(__file__).resolve().parents[3]
    proxy = (root / "infra" / "studio-proxy.conf").read_text()
    compose = (root / "docker-compose.yml").read_text()

    assert '"https://smith.langchain.com" $http_origin;' in proxy
    assert "Access-Control-Allow-Private-Network $studio_cors_true" in proxy
    assert '"OPTIONS:" 1;' in proxy
    assert "studio-proxy:" in compose
    assert '"127.0.0.1:2024:2024"' in compose


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
