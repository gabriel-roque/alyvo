from app.db import SessionLocal
from app.models import OutboxEvent
from sqlalchemy import select


def test_tool_confirmation_is_idempotent_after_success(client, patient_token):
    headers = {"Authorization": f"Bearer {patient_token}"}
    slot = client.get("/api/v1/availability").json()["items"][0]
    session_id = client.post("/api/v1/chat/sessions", headers=headers, json={}).json()["id"]
    prepared = client.post(
        f"/api/v1/chat/sessions/{session_id}/actions",
        headers=headers,
        json={
            "tool": "create_appointment",
            "arguments": {
                "doctor_id": slot["doctor"]["id"],
                "starts_at": slot["starts_at"],
                "reason": "Consulta",
            },
        },
    )
    confirmation = prepared.json()["confirmation_request"]
    assert confirmation["id"]
    completed = client.post(
        f"/api/v1/chat/sessions/{session_id}/confirmations/{confirmation['id']}",
        headers=headers,
        json={"accepted": True},
    )
    assert completed.status_code == 200
    assert completed.json()["tool_result"]["type"] == "appointment_created"
    replay = client.post(
        f"/api/v1/chat/sessions/{session_id}/confirmations/{confirmation['id']}",
        headers=headers,
        json={"accepted": True},
    )
    assert replay.status_code == 200
    assert replay.json()["tool_result"] == completed.json()["tool_result"]


def test_catalog_archive_preserves_outbox(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    created = client.post(
        "/api/v1/backoffice/catalog/insurers", headers=headers, json={"name": "Convênio Temporário"}
    )
    item_id = created.json()["id"]
    assert (
        client.delete(f"/api/v1/backoffice/catalog/insurers/{item_id}", headers=headers).status_code
        == 204
    )
    with SessionLocal() as db:
        deleted = db.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == item_id, OutboxEvent.event_type == "insurers.deleted"
            )
        )
        assert deleted is not None
        assert deleted.payload.get("_correlation_id")


def test_recurring_availability_rule_can_be_created(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    doctor = client.get("/api/v1/backoffice/doctors", headers=headers).json()["items"][0]
    unit = client.get("/api/v1/backoffice/catalog/units", headers=headers).json()["items"][0]
    response = client.post(
        "/api/v1/backoffice/availability-rules",
        headers=headers,
        json={
            "doctor_id": doctor["id"],
            "unit_id": unit["id"],
            "weekday": 5,
            "starts_at": "09:00",
            "ends_at": "12:00",
            "slot_minutes": 30,
        },
    )
    assert response.status_code == 201
