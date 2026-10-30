from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Availability,
    Doctor,
    DocumentStatus,
    Exam,
    Insurer,
    KnowledgeDocument,
    OutboxEvent,
    Role,
    Service,
    Specialty,
    Tenant,
    Unit,
    User,
)
from .security import cpf_lookup, hash_password, protect_cpf


def seed_demo(db: Session) -> None:
    if db.get(Tenant, "clinic-alyvo"):
        return

    primary = Tenant(id="clinic-alyvo", name="Clínica Alyvo")
    isolation = Tenant(id="clinic-isolation", name="Clínica Horizonte")
    db.add_all([primary, isolation])
    db.flush()

    cardiology = Specialty(tenant_id=primary.id, name="Cardiologia", description="Cuidado cardiovascular preventivo.")
    pediatrics = Specialty(tenant_id=primary.id, name="Pediatria", description="Atendimento administrativo pediátrico.")
    center = Unit(tenant_id=primary.id, name="Unidade Centro", address="Rua das Acácias, 320 — São Paulo, SP")
    south = Unit(tenant_id=primary.id, name="Unidade Sul", address="Av. das Flores, 840 — São Paulo, SP")
    vida = Insurer(tenant_id=primary.id, name="Vida+")
    amil = Insurer(tenant_id=primary.id, name="Amil")
    db.add_all([cardiology, pediatrics, center, south, vida, amil])
    db.flush()

    doctors = [
        Doctor(tenant_id=primary.id, name="Dra. Marina Lopes", crm="CRM 123456 SP", specialty_id=cardiology.id, unit_id=center.id, insurer_ids=[vida.id, amil.id]),
        Doctor(tenant_id=primary.id, name="Dr. Lucas Ferreira", crm="CRM 234567 SP", specialty_id=cardiology.id, unit_id=center.id, insurer_ids=[vida.id]),
        Doctor(tenant_id=primary.id, name="Dra. Amanda Prado", crm="CRM 345678 SP", specialty_id=pediatrics.id, unit_id=south.id, insurer_ids=[amil.id]),
    ]
    db.add_all(doctors)
    db.flush()

    consultation = Service(
        tenant_id=primary.id,
        name="Consulta especializada",
        duration_minutes=30,
        specialty_id=cardiology.id,
    )
    blood_exam = Exam(
        tenant_id=primary.id,
        name="Hemograma completo",
        preparation="Confirmar no pedido médico se há necessidade de jejum.",
        unit_ids=[center.id, south.id],
    )
    db.add_all([consultation, blood_exam])
    db.flush()

    today = datetime.now(timezone.utc).date()
    for offset in range(1, 8):
        current = today + timedelta(days=offset)
        if current.weekday() >= 5:
            continue
        for doctor in doctors:
            for slot in (time(9, 0), time(10, 30), time(14, 0), time(16, 30)):
                start = datetime.combine(current, slot, tzinfo=timezone.utc)
                db.add(Availability(tenant_id=primary.id, doctor_id=doctor.id, unit_id=doctor.unit_id, starts_at=start, ends_at=start + timedelta(minutes=30)))

    patient_cpf = "12345678909"
    db.add_all(
        [
            User(tenant_id=primary.id, role=Role.patient, name="Juliana Silva", email="juliana.demo@alyvo.local", cpf_hmac=cpf_lookup(patient_cpf), cpf_encrypted=protect_cpf(patient_cpf)),
            User(tenant_id=primary.id, role=Role.admin, name="Ana Duarte", email="admin@alyvo.local", password_hash=hash_password("alyvo-demo")),
            User(tenant_id=primary.id, role=Role.receptionist, name="Clara Lima", email="recepcao@alyvo.local", password_hash=hash_password("alyvo-demo")),
        ]
    )
    for specialty in (cardiology, pediatrics):
        db.add(OutboxEvent(tenant_id=primary.id, aggregate_type="specialties", aggregate_id=specialty.id, event_type="specialties.upserted", payload={"id": specialty.id, "name": specialty.name}))
    for unit in (center, south):
        db.add(OutboxEvent(tenant_id=primary.id, aggregate_type="units", aggregate_id=unit.id, event_type="units.upserted", payload={"id": unit.id, "name": unit.name, "address": unit.address}))
    for insurer in (vida, amil):
        db.add(OutboxEvent(tenant_id=primary.id, aggregate_type="insurers", aggregate_id=insurer.id, event_type="insurers.upserted", payload={"id": insurer.id, "name": insurer.name}))
    db.add(OutboxEvent(tenant_id=primary.id, aggregate_type="exams", aggregate_id=blood_exam.id, event_type="exams.upserted", payload={"id": blood_exam.id, "name": blood_exam.name, "preparation": blood_exam.preparation, "unit_ids": blood_exam.unit_ids, "active": blood_exam.active}))
    db.add(OutboxEvent(tenant_id=primary.id, aggregate_type="services", aggregate_id=consultation.id, event_type="services.upserted", payload={"id": consultation.id, "name": consultation.name, "duration_minutes": consultation.duration_minutes, "specialty_id": consultation.specialty_id, "active": consultation.active}))
    db.add(OutboxEvent(tenant_id=primary.id, aggregate_type="projection", aggregate_id=primary.id, event_type="projection.v4.rebuild", payload={"id": primary.id, "clinic_name": primary.name}))
    for doctor in doctors:
        db.add(OutboxEvent(tenant_id=primary.id, aggregate_type="doctor", aggregate_id=doctor.id, event_type="doctor.upserted", payload={"id": doctor.id, "name": doctor.name, "crm": doctor.crm, "specialty_id": doctor.specialty_id, "unit_id": doctor.unit_id, "insurer_ids": doctor.insurer_ids}))
    knowledge_documents = [
            KnowledgeDocument(
                tenant_id=primary.id,
                title="Guia de convênios e unidades 2026",
                source="Base institucional aprovada",
                content="A Clínica Alyvo aceita Vida+ e Amil. A Unidade Centro fica na Rua das Acácias, 320. Consultas de cardiologia duram 30 minutos.",
                status=DocumentStatus.published,
                entities=["Vida+", "Amil", "Unidade Centro", "Cardiologia"],
            ),
            KnowledgeDocument(
                tenant_id=primary.id,
                title="Orientações administrativas para exames",
                source="Manual de atendimento v2",
                content="Para exames de sangue, confirme o preparo indicado no pedido médico e apresente documento com foto e carteirinha do convênio. A recepção pode esclarecer exigências administrativas.",
                status=DocumentStatus.published,
                entities=["Exame", "Documento", "Convênio"],
            ),
            KnowledgeDocument(
                tenant_id=isolation.id,
                title="Documento isolado",
                source="Clínica Horizonte",
                content="CONTEÚDO SIGILOSO DO TENANT DE TESTE — nunca deve aparecer na Clínica Alyvo.",
                status=DocumentStatus.published,
            ),
        ]
    db.add_all(knowledge_documents)
    db.flush()
    for document in knowledge_documents:
        chunks = [document.content]
        document.chunks = chunks
        db.add(
            OutboxEvent(
                tenant_id=document.tenant_id,
                aggregate_type="knowledge_document",
                aggregate_id=document.id,
                event_type="knowledge.published",
                payload={
                    "id": document.id,
                    "title": document.title,
                    "source": document.source,
                    "entities": document.entities,
                    "chunks": chunks,
                },
            )
        )
    db.commit()


def ensure_seeded(db: Session) -> None:
    if db.scalar(select(Tenant.id).limit(1)) is None:
        seed_demo(db)
        return
    # One-time rebuild marker for the complete graph schema introduced in v4.
    # It also upgrades persistent demo volumes created by earlier versions.
    if db.scalar(select(OutboxEvent.id).where(OutboxEvent.event_type == "projection.v4.rebuild")):
        return
    for tenant in db.scalars(select(Tenant)).all():
        db.add(OutboxEvent(tenant_id=tenant.id, aggregate_type="projection", aggregate_id=tenant.id, event_type="projection.v4.rebuild", payload={"id": tenant.id, "clinic_name": tenant.name}))
        for model, kind in ((Specialty, "specialties"), (Unit, "units"), (Insurer, "insurers"), (Exam, "exams"), (Service, "services")):
            for item in db.scalars(select(model).where(model.tenant_id == tenant.id)).all():
                if hasattr(item, "active") and not item.active:
                    continue
                payload = {"id": item.id, "name": item.name}
                for field in ("description", "address", "preparation", "unit_ids", "duration_minutes", "specialty_id", "active"):
                    if hasattr(item, field):
                        payload[field] = getattr(item, field)
                db.add(OutboxEvent(tenant_id=tenant.id, aggregate_type=kind, aggregate_id=item.id, event_type=f"{kind}.upserted", payload=payload))
        for doctor in db.scalars(select(Doctor).where(Doctor.tenant_id == tenant.id, Doctor.deleted_at.is_(None))).all():
            db.add(OutboxEvent(tenant_id=tenant.id, aggregate_type="doctor", aggregate_id=doctor.id, event_type="doctor.upserted", payload={"id": doctor.id, "name": doctor.name, "crm": doctor.crm, "specialty_id": doctor.specialty_id, "unit_id": doctor.unit_id, "insurer_ids": doctor.insurer_ids}))
        for document in db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == tenant.id, KnowledgeDocument.status == DocumentStatus.published)).all():
            db.add(OutboxEvent(tenant_id=tenant.id, aggregate_type="knowledge_document", aggregate_id=document.id, event_type="knowledge.published", payload={"id": document.id, "title": document.title, "source": document.source, "entities": document.entities, "chunks": document.chunks or [document.content]}))
    db.commit()

