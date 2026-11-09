from datetime import datetime, timedelta, timezone

import pytest
from app.modules.knowledge.application import ProcessKnowledgeDocument
from app.modules.knowledge.application import jobs as knowledge_jobs
from app.modules.scheduling.domain import CancellationPolicy
from app.shared.infrastructure.database import SessionLocal
from app.shared.infrastructure.models import (
    AuditEvent,
    DocumentStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    OutboxEvent,
)
from sqlalchemy import func, select


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


def test_multiple_knowledge_uploads_are_processed_with_embeddings(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post(
        "/api/v1/backoffice/knowledge/uploads",
        headers=headers,
        files=[
            (
                "files",
                (
                    "horarios.txt",
                    b"A clinica abre de segunda a sexta, das 8h as 18h.",
                    "text/plain",
                ),
            ),
            (
                "files",
                ("retornos.md", b"# Retornos\nO retorno ocorre em ate 30 dias.", "text/markdown"),
            ),
        ],
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["total"] == 2

    for document in payload["items"]:
        result = ProcessKnowledgeDocument().execute(document["id"])
        assert result["status"] == "review_required"
        repeated = ProcessKnowledgeDocument().execute(document["id"])
        assert repeated["idempotent"] is True

    document_ids = [document["id"] for document in payload["items"]]
    with SessionLocal() as session:
        chunks = session.scalar(
            select(func.count(KnowledgeChunk.id)).where(
                KnowledgeChunk.document_id.in_(document_ids),
                KnowledgeChunk.embedding != [],
            )
        )
        assert chunks == 2


def test_knowledge_processing_persists_failure_reason(client, admin_token, monkeypatch):
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = client.post(
        "/api/v1/backoffice/knowledge/uploads",
        headers=headers,
        files=[("files", ("ilegivel.png", b"not-an-image", "image/png"))],
    )
    document_id = response.json()["items"][0]["id"]

    class BrokenOcr:
        def extract(self, content, filename):
            raise RuntimeError("OCR indisponivel")

    monkeypatch.setattr(knowledge_jobs, "ocr_provider", lambda: BrokenOcr())
    with pytest.raises(RuntimeError, match="OCR indisponivel"):
        ProcessKnowledgeDocument().execute(document_id)

    with SessionLocal() as session:
        document = session.get(KnowledgeDocument, document_id)
        assert document is not None
        assert document.status == DocumentStatus.failed
        assert document.error == "RuntimeError: OCR indisponivel"


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
