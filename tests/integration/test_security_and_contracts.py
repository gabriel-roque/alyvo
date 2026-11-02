from app.ai.providers import ChatModelProvider, DeterministicChatProvider, OpenRouterChatProvider
from app.config import Settings


def test_unknown_patient_can_register_with_signed_context(client):
    identified = client.post("/api/v1/auth/patient/identify", json={"cpf": "111.222.333-44", "birth_date": "1995-05-20"})
    assert identified.status_code == 200
    token = identified.json()["registration_token"]
    invalid = client.post("/api/v1/auth/patient/register", json={"name": "Paciente Novo", "email": "novo.paciente@alyvo.local", "registration_token": "invalid"})
    assert invalid.status_code == 401
    created = client.post("/api/v1/auth/patient/register", json={"name": "Paciente Novo", "email": "novo.paciente@alyvo.local", "registration_token": token})
    assert created.status_code == 201
    assert created.json()["access_token"]


def test_refresh_rotation_and_logout_revoke_staff_tokens(client):
    login = client.post("/api/v1/auth/staff/login", json={"email": "admin@alyvo.local", "password": "alyvo-demo"}).json()
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refreshed.status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}).status_code == 401
    current = refreshed.json()["refresh_token"]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": current}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": current}).status_code == 401


def test_receptionist_cannot_mutate_admin_catalog(client):
    login = client.post("/api/v1/auth/staff/login", json={"email": "recepcao@alyvo.local", "password": "alyvo-demo"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/backoffice/catalog/exams", headers=headers).status_code == 200
    assert client.post("/api/v1/backoffice/catalog/exams", headers=headers, json={"name": "Exame indevido"}).status_code == 403


def test_provider_swap_preserves_chat_contract(client):
    assert isinstance(DeterministicChatProvider(), ChatModelProvider)
    assert isinstance(OpenRouterChatProvider(Settings(openrouter_api_key="synthetic")), ChatModelProvider)
    schema = client.get("/openapi.json").json()
    assert "200" in schema["paths"]["/api/v1/chat/sessions/{session_id}/messages"]["post"]["responses"]
