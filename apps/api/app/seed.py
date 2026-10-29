from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Availability,
    Doctor,
    DocumentStatus,
    Insurer,
    KnowledgeDocument,
    Role,
    Specialty,
    Tenant,
    Unit,
    User,
)
from .security import cpf_lookup, protect_cpf


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
            User(tenant_id=primary.id, role=Role.admin, name="Ana Duarte", email="admin@alyvo.local"),
            User(tenant_id=primary.id, role=Role.receptionist, name="Clara Lima", email="recepcao@alyvo.local"),
        ]
    )
    db.add_all(
        [
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
    )
    db.commit()


def ensure_seeded(db: Session) -> None:
    if db.scalar(select(Tenant.id).limit(1)) is None:
        seed_demo(db)

