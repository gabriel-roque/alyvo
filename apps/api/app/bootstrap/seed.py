from __future__ import annotations

from datetime import date, time

from sqlalchemy.orm import Session

from app.bootstrap.config import Settings, get_settings
from app.modules.identity.infrastructure.security import cpf_lookup, hash_password, protect_cpf
from app.modules.knowledge.application import structural_chunks
from app.shared.infrastructure.database import AdminSessionLocal
from app.shared.infrastructure.models import (
    AvailabilityRule,
    ClinicProfile,
    Doctor,
    DocumentStatus,
    Exam,
    Insurer,
    KnowledgeChunk,
    KnowledgeDocument,
    OutboxEvent,
    Role,
    Specialty,
    Unit,
    User,
)


def _create_catalog(session: Session, settings: Settings):
    profile = ClinicProfile(id=1, name=settings.clinic_name, timezone=settings.clinic_timezone)
    cardiology = Specialty(name="Cardiologia", description="Cuidado cardiovascular")
    pediatrics = Specialty(name="Pediatria", description="Atendimento infantil")
    center = Unit(name="Unidade Centro", address="Av. Central, 100")
    south = Unit(name="Unidade Sul", address="Rua das Flores, 220")
    unimed, vida = Insurer(name="UNIMED"), Insurer(name="Vida+")
    session.add_all([profile, cardiology, pediatrics, center, south, unimed, vida])
    session.flush()
    doctors = (
        Doctor(
            name="Dra. Marina Costa",
            crm="CRM 12345",
            specialty=cardiology,
            unit=center,
            insurers=[unimed, vida],
        ),
        Doctor(
            name="Dr. Paulo Lima",
            crm="CRM 67890",
            specialty=pediatrics,
            unit=south,
            insurers=[unimed],
        ),
    )
    session.add_all(
        [
            *doctors,
            Exam(name="Hemograma", preparation="Jejum não obrigatório", units=[center, south]),
        ]
    )
    session.flush()
    return (cardiology, pediatrics), (center, south), (unimed, vida), doctors


def _create_users(session: Session) -> None:
    session.add_all(
        [
            User(
                role=Role.admin,
                name="Admin Alyvo",
                email="admin@alyvo.local",
                password_hash=hash_password("alyvo-demo"),
            ),
            User(
                role=Role.receptionist,
                name="Recepção Alyvo",
                email="recepcao@alyvo.local",
                password_hash=hash_password("alyvo-demo"),
            ),
            User(
                role=Role.patient,
                name="Juliana Demo",
                email="juliana.demo@alyvo.local",
                password_hash=None,
                cpf_hmac=cpf_lookup("12345678909"),
                cpf_encrypted=protect_cpf("12345678909"),
                birth_date=date(1990, 1, 15),
            ),
        ]
    )


def _create_rules(session: Session, doctors, units) -> None:
    for doctor, unit in zip(doctors, units, strict=True):
        for weekday in range(5):
            session.add(
                AvailabilityRule(
                    doctor_id=doctor.id,
                    unit_id=unit.id,
                    weekday=weekday,
                    starts_at=time(8),
                    ends_at=time(18),
                    slot_minutes=30,
                )
            )


def _create_knowledge(session: Session, settings: Settings):
    document = KnowledgeDocument(
        title="Guia institucional Alyvo",
        content="A clínica atende de segunda a sexta, das 8h às 18h. Resultados de hemograma ficam disponíveis em até dois dias úteis.",
        status=DocumentStatus.published,
        source="Base institucional",
    )
    session.add(document)
    session.flush()
    chunks = structural_chunks(document.content)
    for position, chunk in enumerate(chunks):
        session.add(
            KnowledgeChunk(
                document_id=document.id,
                position=position,
                content=chunk.content,
                content_hash=chunk.content_hash,
                section=chunk.section,
                page=chunk.page,
                parent_id=chunk.parent_id,
                parser_version=settings.chunk_parser_version,
                embedding_model=settings.embedding_model,
                index_version=settings.knowledge_index_version,
            )
        )
    return document, chunks


def _catalog_events(session: Session, groups) -> None:
    for resource, items in groups:
        for item in items:
            session.add(
                OutboxEvent(
                    aggregate_type=resource,
                    aggregate_id=item.id,
                    event_type=f"{resource}.created",
                    payload={"id": item.id, "name": item.name, "active": item.active},
                )
            )


def _create_outbox(
    session: Session, settings: Settings, catalogs, units, insurers, doctors, document, chunks
) -> None:
    session.add(
        OutboxEvent(
            aggregate_type="system",
            aggregate_id="seed",
            event_type="projection.rebuild",
            payload={"reason": "initial-seed"},
        )
    )
    session.flush()
    _catalog_events(session, (("specialties", catalogs), ("units", units), ("insurers", insurers)))
    for doctor in doctors:
        session.add(
            OutboxEvent(
                aggregate_type="doctor",
                aggregate_id=doctor.id,
                event_type="doctor.created",
                payload={
                    "id": doctor.id,
                    "name": doctor.name,
                    "crm": doctor.crm,
                    "specialty_id": doctor.specialty_id,
                    "unit_id": doctor.unit_id,
                    "insurer_ids": [item.id for item in doctor.insurers],
                },
            )
        )
    session.add(
        OutboxEvent(
            aggregate_type="knowledge_document",
            aggregate_id=document.id,
            event_type="knowledge.published",
            payload={
                "id": document.id,
                "title": document.title,
                "source": document.source,
                "entities": [],
                "chunks": [
                    {
                        "content": chunk.content,
                        "content_hash": chunk.content_hash,
                        "section": chunk.section,
                        "page": chunk.page,
                        "parent_id": chunk.parent_id,
                        "parser_version": settings.chunk_parser_version,
                        "embedding_model": settings.embedding_model,
                        "index_version": settings.knowledge_index_version,
                    }
                    for chunk in chunks
                ],
            },
        )
    )


def seed() -> None:
    settings = get_settings()
    with AdminSessionLocal.begin() as session:
        if session.get(ClinicProfile, 1):
            return
        catalogs, units, insurers, doctors = _create_catalog(session, settings)
        _create_users(session)
        _create_rules(session, doctors, units)
        document, chunks = _create_knowledge(session, settings)
        _create_outbox(session, settings, catalogs, units, insurers, doctors, document, chunks)


if __name__ == "__main__":
    seed()
