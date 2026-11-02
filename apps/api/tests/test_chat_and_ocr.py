import httpx
from app.ai.providers import OllamaChatProvider
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


def test_ollama_timeout_returns_grounded_fallback(monkeypatch):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("modelo local em aquecimento")
    monkeypatch.setattr("app.ai.providers.httpx.post", timeout)
    provider = OllamaChatProvider(Settings())
    answer = provider.complete("Onde atende?", ["Dra. Marina atende na Unidade Centro."])
    assert "Unidade Centro" in answer
