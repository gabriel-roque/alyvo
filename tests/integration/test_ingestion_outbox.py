from app.db import SessionLocal
from app.models import OutboxEvent
from sqlalchemy import select


def test_approved_ingestion_creates_tenant_scoped_outbox_event(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    created = client.post(
        "/api/v1/backoffice/ingestions",
        headers=headers,
        json={
            "title": "Nova regra sintética",
            "content": "A Unidade Centro aceita o convênio Vida+ para cardiologia.",
        },
    )
    assert created.status_code == 201
    document_id = created.json()["id"]
    approved = client.post(
        f"/api/v1/backoffice/ingestions/{document_id}/approve",
        headers=headers,
        json={"entities": [{"type": "Insurer", "name": "Vida+"}], "confirmed": True},
    )
    assert approved.status_code == 200
    with SessionLocal() as db:
        event = db.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == document_id,
                OutboxEvent.event_type == "knowledge.published",
            )
        )
        assert event is not None
        assert event.tenant_id == "clinic-alyvo"

