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


def test_conversation_context_is_persisted_between_messages(client):
    session_id = client.post("/api/v1/chat/sessions").json()["id"]
    first = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"content": "Quero ver horários disponíveis"},
    )
    second = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"content": "Na próxima sexta-feira"},
    )
    third = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"content": "E à tarde?"},
    )

    assert first.json()["intent"] == "clarify_availability"
    assert second.json()["intent"] == "search_availability"
    assert third.json()["intent"] == "search_availability"
    assert third.json()["tool_result"]["period"] == "afternoon"


def test_conversation_tool_policy_paths(client, patient_token):
    session_id = client.post("/api/v1/chat/sessions").json()["id"]
    invalid = client.post(
        f"/api/v1/chat/sessions/{session_id}/actions",
        json={"tool": "unknown_tool", "arguments": {}},
    )
    assert invalid.status_code == 422

    direct = client.post(
        f"/api/v1/chat/sessions/{session_id}/actions",
        json={"tool": "list_insurers", "arguments": {}},
    )
    assert direct.status_code == 200
    assert direct.json()["tool_result"]["type"] == "insurers"

    pending = client.post(
        f"/api/v1/chat/sessions/{session_id}/actions",
        json={"tool": "list_my_appointments", "arguments": {}},
    )
    assert pending.status_code == 200
    assert pending.json()["auth_required"] is True

    headers = {"Authorization": f"Bearer {patient_token}"}
    resumed = client.post(f"/api/v1/chat/sessions/{session_id}/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["tool_result"]["type"] == "appointments"

    no_pending_session = client.post("/api/v1/chat/sessions", headers=headers).json()["id"]
    assert (
        client.post(
            f"/api/v1/chat/sessions/{no_pending_session}/resume", headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/chat/sessions/{session_id}/confirmations/missing",
            headers=headers,
            json={"accepted": True},
        ).status_code
        == 404
    )


def test_confirmation_can_be_rejected_only_once(client, patient_token):
    headers = {"Authorization": f"Bearer {patient_token}"}
    session_id = client.post("/api/v1/chat/sessions", headers=headers).json()["id"]
    doctor = client.get("/api/v1/directory/doctors").json()["items"][0]
    prepared = client.post(
        f"/api/v1/chat/sessions/{session_id}/actions",
        headers=headers,
        json={
            "tool": "create_appointment",
            "arguments": {
                "doctor_id": doctor["id"],
                "starts_at": (datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
                "reason": "Operação rejeitada",
            },
        },
    )
    confirmation_id = prepared.json()["confirmation_request"]["id"]
    rejected = client.post(
        f"/api/v1/chat/sessions/{session_id}/confirmations/{confirmation_id}",
        headers=headers,
        json={"accepted": False},
    )
    assert rejected.status_code == 200
    assert rejected.json()["answer"] == "Operação cancelada."
    assert (
        client.post(
            f"/api/v1/chat/sessions/{session_id}/confirmations/{confirmation_id}",
            headers=headers,
            json={"accepted": False},
        ).status_code
        == 409
    )


def test_directory_understands_specialty_and_insurer_in_natural_language(client):
    response = client.get(
        "/api/v1/directory/doctors",
        params={"q": "Quais cardiologistas aceitam Vida+?"},
    )

    assert response.status_code == 200
    assert [doctor["name"] for doctor in response.json()["items"]] == ["Dra. Marina Costa"]


def test_patient_can_correct_the_date_and_reschedule_through_chat(client, patient_token):
    headers = {"Authorization": f"Bearer {patient_token}"}
    doctor = client.get("/api/v1/directory/doctors", params={"q": "Cardiologia"}).json()["items"][0]
    target = (datetime.now(timezone.utc) + timedelta(days=10)).date()
    while target.weekday() > 4:
        target += timedelta(days=1)
    availability = client.get(
        "/api/v1/appointments/availability",
        params={"from_date": target.isoformat(), "doctor_id": doctor["id"]},
    ).json()["items"]
    assert availability
    created = client.post(
        "/api/v1/appointments",
        headers=headers,
        json={
            "doctor_id": doctor["id"],
            "starts_at": availability[0]["starts_at"],
            "reason": "Consulta para remarcação",
        },
    )
    assert created.status_code == 201
    appointment_id = created.json()["id"]

    session_id = client.post("/api/v1/chat/sessions", headers=headers).json()["id"]
    request = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": "Desculpa, falei o dia errado. Tem como remarcar?"},
    )
    assert request.status_code == 200
    assert request.json()["intent"] == "list_my_appointments"

    selected = client.post(
        f"/api/v1/chat/sessions/{session_id}/actions",
        headers=headers,
        json={"tool": "start_reschedule", "arguments": {"appointment_id": appointment_id}},
    )
    assert selected.status_code == 200
    assert selected.json()["tool_result"]["type"] == "reschedule_started"

    new_target = target + timedelta(days=7)
    options = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        headers=headers,
        json={"content": f"Quero remarcar para {new_target.isoformat()}"},
    )
    assert options.status_code == 200
    result = options.json()["tool_result"]
    assert result["type"] == "availability"
    assert result["reschedule_appointment_id"] == appointment_id
    assert result["items"]

    prepared = client.post(
        f"/api/v1/chat/sessions/{session_id}/actions",
        headers=headers,
        json={
            "tool": "reschedule_appointment",
            "arguments": {
                "appointment_id": appointment_id,
                "starts_at": result["items"][0]["starts_at"],
            },
        },
    )
    assert prepared.status_code == 200
    confirmation_id = prepared.json()["confirmation_request"]["id"]
    confirmed = client.post(
        f"/api/v1/chat/sessions/{session_id}/confirmations/{confirmation_id}",
        headers=headers,
        json={"accepted": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["tool_result"]["type"] == "appointment_rescheduled"
