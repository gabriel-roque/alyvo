from datetime import datetime
from zoneinfo import ZoneInfo

from app.ai.conversation import resolve_date_window


def test_structured_directory_uses_operational_source(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    response = client.post(f"/api/v1/chat/sessions/{session}/messages", json={"content": "Quais cardiologistas aceitam o convênio Vida+ na Unidade Centro?"})
    body = response.json()
    assert response.status_code == 200
    assert body["intent"] == "search_directory"
    assert body["tool_result"]["type"] == "directory"
    assert {item["doctor"] for item in body["tool_result"]["items"]} == {"Dra. Marina Lopes", "Dr. Lucas Ferreira"}


def test_personal_tool_requests_identification(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    response = client.post(f"/api/v1/chat/sessions/{session}/messages", json={"content": "Quais são minhas consultas?"})
    assert response.status_code == 200
    assert response.json()["auth_required"] is True
    assert response.json()["tool_call"]["name"] == "list_my_appointments"


def test_authenticated_resume_consumes_checkpointed_tool(client, patient_token):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    requested = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Quais são minhas consultas?"},
    )
    assert requested.json()["auth_required"] is True
    headers = {"Authorization": f"Bearer {patient_token}"}
    resumed = client.post(f"/api/v1/chat/sessions/{session}/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["tool_call"]["name"] == "list_my_appointments"
    replay = client.post(f"/api/v1/chat/sessions/{session}/resume", headers=headers)
    assert replay.status_code == 409


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


def test_compound_greeting_does_not_trigger_rag(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    body = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Olá, bom dia!"},
    ).json()
    assert body["intent"] == "conversation"
    assert body["citations"] == []
    assert body["answer"].startswith("Bom dia!")


def test_catalog_questions_use_explicit_tools(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    insurers = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Quais planos de saúde vocês atendem?"},
    ).json()
    assert insurers["intent"] == "list_insurers"
    assert insurers["tool_result"]["type"] == "insurers"
    assert all("doctor" not in item for item in insurers["tool_result"]["items"])

    exams = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Quais exames vocês realizam?"},
    ).json()
    assert exams["intent"] == "list_exams"
    assert exams["tool_result"]["type"] == "exams"
    assert all("doctor" not in item for item in exams["tool_result"]["items"])


def test_capabilities_are_not_answered_by_rag(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    body = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "No que você pode me ajudar?"},
    ).json()
    assert body["intent"] == "capabilities"
    assert body["citations"] == []
    assert "convênios" in body["answer"]


def test_follow_up_keeps_context_for_scheduling(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    first = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Quero marcar uma consulta com a Dra. Amanda"},
    )
    assert first.json()["intent"] == "search_availability"
    assert "unit" not in (first.json().get("resolved_request") or {})
    second = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Na sexta-feira à tarde"},
    )
    assert second.json()["intent"] == "search_availability"
    assert second.json()["tool_result"]["type"] == "availability"
    assert second.json()["resolved_request"]["doctor"] == "Dra. Amanda Prado"
    assert second.json()["resolved_request"]["period"] == "afternoon"
    assert datetime.fromisoformat(second.json()["resolved_request"]["from"]).weekday() == 4


def test_typo_and_abbreviated_unit_are_understood(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    directory = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "qro um cardeologista"},
    ).json()
    assert directory["intent"] == "search_directory"
    assert {item["specialty"] for item in directory["tool_result"]["items"]} == {"Cardiologia"}

    vague = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "tem orario?"},
    ).json()
    assert vague["intent"] == "search_availability"
    assert "qual dia" in vague["answer"].casefold()

    refined = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "amanha de tarde na unid sul"},
    ).json()
    assert refined["resolved_request"]["unit"] == "Unidade Sul"
    assert refined["resolved_request"]["period"] == "afternoon"
    assert all(item["unit"]["name"] == "Unidade Sul" for item in refined["tool_result"]["items"])


def test_schedule_context_and_unit_address_use_operational_data(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    schedule = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Esses horários são no horário de São Paulo? A clínica abre às 6h?"},
    ).json()
    assert schedule["intent"] == "schedule_information"
    assert "horário de Brasília" in schedule["answer"]
    assert "08:00" in schedule["answer"]

    address = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Onde fica a Unidade Centro?"},
    ).json()
    assert address["intent"] == "search_directory"
    assert "Rua das Acácias, 320" in address["answer"]


def test_specialty_with_relative_date_routes_to_availability(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    response = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Quero um cardiologista amanhã"},
    ).json()
    assert response["intent"] == "search_availability"
    assert response["resolved_request"]["specialty"] == "Cardiologia"
    assert response["resolved_request"]["from"]


def test_relative_friday_is_resolved_in_clinic_timezone():
    now = datetime(2026, 11, 2, 10, tzinfo=ZoneInfo("America/Sao_Paulo"))
    window = resolve_date_window("Tem horários na sexta-feira?", now=now)
    assert window is not None
    assert window.start.isoformat() == "2026-11-06"
    next_window = resolve_date_window("Na próxima sexta", now=datetime(2026, 11, 6, 10, tzinfo=ZoneInfo("America/Sao_Paulo")))
    assert next_window is not None
    assert next_window.start.isoformat() == "2026-11-13"


def test_day_of_current_month_is_resolved():
    now = datetime(2026, 11, 2, 10, tzinfo=ZoneInfo("America/Sao_Paulo"))
    window = resolve_date_window("Marcar consulta para dia 15 desse mês", now=now)
    assert window is not None
    assert window.start.isoformat() == "2026-11-15"


def test_stream_endpoint_emits_status_and_final(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    response = client.post(
        f"/api/v1/chat/sessions/{session}/messages/stream",
        json={"content": "Horários na sexta-feira"},
    )
    assert response.status_code == 200
    assert "event: status" in response.text
    assert "event: final" in response.text
    assert "sexta-feira" in response.text
