from io import BytesIO

from app.ai.workflow import ConversationState
from app.db import SessionLocal
from app.models import OutboxEvent, PatientDocument
from sqlalchemy import select


def test_langgraph_state_and_transactional_tool_execution(client, patient_token):
    required = {
        "session_id", "entities", "missing_data", "attachments", "retrievals",
        "pending_action", "tool_result", "history_summary", "correlation_id",
    }
    assert required <= set(ConversationState.__annotations__)
    headers = {"Authorization": f"Bearer {patient_token}"}
    slot = client.get("/api/v1/availability").json()["items"][0]
    session_id = client.post("/api/v1/chat/sessions", headers=headers, json={}).json()["id"]
    response = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        headers=headers,
        json={
            "content": "Confirmo este agendamento",
            "confirmed": True,
            "action": {"type": "schedule", "doctor_id": slot["doctor"]["id"], "starts_at": slot["starts_at"]},
        },
    )
    assert response.status_code == 200
    assert response.json()["tool_result"]["type"] == "appointment_created"
    assert "execute_tools" in response.json()["graph_trace"]


def test_sse_contract_has_incremental_tokens_and_error(client):
    session_id = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"content": "Faça meu diagnóstico e prescreva um remédio"},
    )
    stream = client.get(f"/api/v1/chat/sessions/{session_id}/events")
    assert stream.status_code == 200
    assert stream.text.count("event: token") >= 2
    assert "event: status" in stream.text
    assert "event: completed" in stream.text

    empty_session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    empty = client.get(f"/api/v1/chat/sessions/{empty_session}/events")
    assert "event: error" in empty.text


def test_chat_attachment_is_private_draft_until_patient_confirmation(client, patient_token, admin_token):
    patient_headers = {"Authorization": f"Bearer {patient_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    session_id = client.post("/api/v1/chat/sessions", headers=patient_headers, json={}).json()["id"]
    upload = client.post(
        f"/api/v1/chat/sessions/{session_id}/attachments",
        headers=patient_headers,
        files={"file": ("identidade-demo.png", BytesIO(b"\x89PNG\r\n\x1a\nsynthetic-image"), "image/png")},
        data={"kind": "identity"},
    )
    assert upload.status_code == 202
    document = upload.json()
    assert document["fields"]
    with SessionLocal() as db:
        stored = db.scalar(select(PatientDocument).where(PatientDocument.id == document["id"]))
        assert stored.fields == {}
        assert stored.confidence == {}
        assert stored.confirmed is False
    backoffice = client.get("/api/v1/backoffice/patient-documents", headers=admin_headers).json()["items"]
    assert document["id"] not in {item["id"] for item in backoffice}
    confirmed = client.post(
        f"/api/v1/patient/documents/{document['id']}/confirm",
        headers=patient_headers,
        json={"fields": document["fields"], "confirmed": True},
    )
    assert confirmed.status_code == 200
    visible = client.get("/api/v1/backoffice/patient-documents", headers=admin_headers).json()["items"]
    assert document["id"] in {item["id"] for item in visible}


def test_backoffice_configuration_crud_and_deletion_outbox(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    clinic = client.patch(
        "/api/v1/backoffice/clinic",
        headers=headers,
        json={"name": "Clínica Alyvo", "timezone": "America/Sao_Paulo"},
    )
    assert clinic.status_code == 200
    created_user = client.post(
        "/api/v1/backoffice/users",
        headers=headers,
        json={"name": "Recepção Teste", "email": "recepcao.teste@alyvo.local", "role": "receptionist", "password": "senha-segura"},
    )
    assert created_user.status_code == 201
    assert client.delete(f"/api/v1/backoffice/users/{created_user.json()['id']}", headers=headers).status_code == 204

    created = client.post(
        "/api/v1/backoffice/catalog/insurers",
        headers=headers,
        json={"name": "Convênio Temporário"},
    )
    item_id = created.json()["id"]
    assert client.delete(f"/api/v1/backoffice/catalog/insurers/{item_id}", headers=headers).status_code == 204
    with SessionLocal() as db:
        deleted = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == item_id, OutboxEvent.event_type == "insurers.deleted"))
        assert deleted is not None
        assert deleted.payload.get("_correlation_id")

    specialty = client.get("/api/v1/backoffice/catalog/specialties", headers=headers).json()["items"][0]
    unit = client.get("/api/v1/backoffice/catalog/units", headers=headers).json()["items"][0]
    insurer = client.get("/api/v1/backoffice/catalog/insurers", headers=headers).json()["items"][0]
    doctor = client.post(
        "/api/v1/backoffice/doctors",
        headers=headers,
        json={
            "name": "Médica Temporária",
            "crm": "CRM-TEMP",
            "specialty_id": specialty["id"],
            "unit_id": unit["id"],
            "insurer_ids": [insurer["id"]],
        },
    )
    assert doctor.status_code == 201
    doctor_id = doctor.json()["id"]
    assert client.delete(f"/api/v1/backoffice/doctors/{doctor_id}", headers=headers).status_code == 204
    visible_doctors = client.get("/api/v1/backoffice/doctors", headers=headers).json()["items"]
    assert doctor_id not in {item["id"] for item in visible_doctors}

