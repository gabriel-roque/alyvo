import httpx
from app.ai.providers import ModelTurn, OllamaChatProvider, ToolCall
from app.config import Settings


def test_public_rag_answer_has_sources(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    response = client.post(f"/api/v1/chat/sessions/{session}/messages", json={"content": "Quais cardiologistas aceitam o convênio Vida+ na Unidade Centro?"})
    body = response.json()
    assert response.status_code == 200
    assert body["intent"] == "search_knowledge"
    assert body["citations"]
    assert body["confidence"] >= 0.6


def test_personal_tool_requests_identification(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    response = client.post(f"/api/v1/chat/sessions/{session}/messages", json={"content": "Quais são minhas consultas?"})
    assert response.status_code == 200
    assert response.json()["auth_required"] is True
    assert response.json()["tool_call"]["name"] == "list_my_appointments"


def test_clinical_request_is_refused(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    response = client.post(f"/api/v1/chat/sessions/{session}/messages", json={"content": "Faça meu diagnóstico e prescreva um remédio"})
    assert response.json()["intent"] == "clinical_safety"
    assert "Não faço diagnóstico" in response.json()["answer"]


def test_greeting_is_conversational_and_does_not_trigger_rag(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    response = client.post(f"/api/v1/chat/sessions/{session}/messages", json={"content": "Bom dia!"})
    body = response.json()
    assert body["intent"] == "conversation"
    assert body["citations"] == []
    assert body["answer"].startswith("Bom dia!")


def test_follow_up_keeps_context_for_scheduling(client, monkeypatch):
    captured = []

    class ContextAwareProvider:
        def respond(self, messages, tools):
            captured.append(messages)
            if len([item for item in messages if item["role"] == "user"]) == 1:
                return ModelTurn("Para qual data você prefere?", [])
            return ModelTurn("", [ToolCall("search_availability", {"doctor": "Amanda"})])

    monkeypatch.setattr("app.ai.workflow.chat_provider", lambda: ContextAwareProvider())
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    first = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Quero marcar uma consulta com a Dra. Amanda"},
    )
    assert first.json()["intent"] == "conversation"
    second = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Amanhã, consulta de rotina"},
    )
    assert second.json()["intent"] == "search_availability"
    assert second.json()["tool_result"]["type"] == "availability"
    assert any(
        item["role"] == "user" and "Dra. Amanda" in item["content"]
        for item in captured[-1]
    )


def test_ollama_timeout_returns_grounded_fallback(monkeypatch):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("modelo local em aquecimento")
    monkeypatch.setattr("app.ai.providers.httpx.post", timeout)
    provider = OllamaChatProvider(Settings())
    answer = provider.complete("Onde atende?", ["Dra. Marina atende na Unidade Centro."])
    assert "Unidade Centro" in answer
