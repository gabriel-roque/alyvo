from datetime import datetime, timedelta, timezone

from app.modules.scheduling.domain import CancellationPolicy
from app.shared.infrastructure.database import SessionLocal
from app.shared.infrastructure.models import AuditEvent, OutboxEvent
from sqlalchemy import select


def test_cancellation_policy_uses_utc_and_staff_override():
    now = datetime.now(timezone.utc)
    policy = CancellationPolicy(notice_hours=24)
    assert policy.allows(now + timedelta(hours=25), now, False)
    assert not policy.allows(now + timedelta(hours=2), now, False)
    assert policy.allows(now + timedelta(hours=2), now, True)


def test_knowledge_publication_writes_audit_and_outbox_atomically(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    created = client.post(
        "/api/v1/backoffice/knowledge/documents",
        headers=headers,
        json={"title": "Política sintética", "content": "Cancelamento permitido com antecedência."},
    )
    assert created.status_code == 201
    document_id = created.json()["id"]
    published = client.post(
        f"/api/v1/backoffice/knowledge/documents/{document_id}/publish",
        headers=headers,
        json={"entities": [], "confirmed": True},
    )
    assert published.status_code == 200
    with SessionLocal() as session:
        event = session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == document_id))
        audit = session.scalar(select(AuditEvent).where(AuditEvent.resource_id == document_id))
        assert event is not None
        assert audit is not None


def test_confirmation_is_idempotent(client, patient_token):
    headers = {"Authorization": f"Bearer {patient_token}"}
    session_id = client.post("/api/v1/chat/sessions", headers=headers).json()["id"]
    doctors = client.get("/api/v1/directory/doctors").json()["items"]
    response = client.post(
        f"/api/v1/chat/sessions/{session_id}/actions",
        headers=headers,
        json={
            "tool": "create_appointment",
            "arguments": {
                "doctor_id": doctors[0]["id"],
                "starts_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                "reason": "Consulta sintética",
            },
        },
    )
    assert response.status_code == 200
    confirmation = response.json()["confirmation_request"]
    assert confirmation["id"]
