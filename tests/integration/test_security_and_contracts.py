from app.ai.providers import ChatModelProvider, DeterministicChatProvider, OpenRouterChatProvider
from app.config import Settings


def test_unknown_patient_can_register_only_with_verified_registration_token(client):
    cpf = "111.222.333-44"
    started = client.post(
        "/api/v1/auth/patient/start",
        json={"cpf": cpf, "email": "novo.paciente@alyvo.local"},
    )
    assert started.status_code == 200
    verified = client.post(
        "/api/v1/auth/patient/verify",
        json={"cpf": cpf, "code": "123456"},
    )
    assert verified.status_code == 200
    token = verified.json()["registration_token"]
    invalid = client.post(
        "/api/v1/auth/patient/register",
        json={"cpf": cpf, "name": "Paciente Novo", "email": "novo.paciente@alyvo.local", "registration_token": "invalid"},
    )
    assert invalid.status_code == 401
    created = client.post(
        "/api/v1/auth/patient/register",
        json={"cpf": cpf, "name": "Paciente Novo", "email": "novo.paciente@alyvo.local", "registration_token": token},
    )
    assert created.status_code == 201
    assert created.json()["access_token"]


def test_refresh_rotation_and_logout_revoke_tokens(client):
    login = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "admin@alyvo.local", "password": "alyvo-demo"},
    ).json()
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert refreshed.status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}).status_code == 401
    current = refreshed.json()["refresh_token"]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": current}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": current}).status_code == 401


def test_receptionist_cannot_mutate_admin_catalog(client):
    login = client.post(
        "/api/v1/auth/staff/login",
        json={"email": "recepcao@alyvo.local", "password": "alyvo-demo"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/backoffice/catalog/exams", headers=headers).status_code == 200
    assert client.post(
        "/api/v1/backoffice/catalog/exams",
        headers=headers,
        json={"name": "Exame indevido"},
    ).status_code == 403


def test_patient_document_never_enters_shared_knowledge(client, patient_token):
    headers = {"Authorization": f"Bearer {patient_token}"}
    uploaded = client.post(
        "/api/v1/patient/documents",
        headers=headers,
        data={"kind": "insurance_card"},
        files={"file": ("carteirinha.png", b"\x89PNG\r\n\x1a\nsynthetic", "image/png")},
    )
    assert uploaded.status_code == 202
    document = uploaded.json()
    secret = "PACIENTE-PRIVADO-NUNCA-RAG"
    confirmed = client.post(
        f"/api/v1/patient/documents/{document['id']}/confirm",
        headers=headers,
        json={"confirmed": True, "fields": {**document["fields"], "observacao": secret}},
    )
    assert confirmed.status_code == 200
    session = client.post("/api/v1/chat/sessions", json={"tenant_id": "clinic-alyvo"}).json()["id"]
    answer = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": secret},
    ).json()
    evidence = answer["answer"] + " " + " ".join(item["excerpt"] for item in answer["citations"])
    assert secret not in evidence


def test_provider_swap_preserves_chat_contract(client):
    local = DeterministicChatProvider()
    external = OpenRouterChatProvider(Settings(openrouter_api_key="synthetic"))
    assert isinstance(local, ChatModelProvider)
    assert isinstance(external, ChatModelProvider)
    schema = client.get("/openapi.json").json()
    response_schema = schema["paths"]["/api/v1/chat/sessions/{session_id}/messages"]["post"]["responses"]
    assert "200" in response_schema
