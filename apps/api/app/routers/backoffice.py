from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.providers import object_storage_provider
from app.config import get_settings
from app.db import get_db
from app.models import (
    Appointment,
    AppointmentHistory,
    AppointmentStatus,
    AuditEvent,
    AvailabilityBlock,
    AvailabilityRule,
    Doctor,
    DocumentStatus,
    Exam,
    Insurer,
    KnowledgeDocument,
    OutboxEvent,
    Role,
    Specialty,
    Unit,
    User,
)
from app.observability import correlation_id
from app.routers.operations import available_slots
from app.security import current_identity, mask_cpf, require_admin, require_staff

router = APIRouter(prefix="/backoffice", tags=["backoffice"])


class DoctorPayload(BaseModel):
    name: str
    crm: str
    specialty_id: str
    unit_id: str
    insurer_ids: list[str] = Field(default_factory=list)
    active: bool = True


class CatalogPayload(BaseModel):
    name: str
    description: str = ""
    address: str = ""
    preparation: str = ""
    unit_ids: list[str] = Field(default_factory=list)
    active: bool = True


class AvailabilityRulePayload(BaseModel):
    doctor_id: str
    unit_id: str
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time
    slot_minutes: int = Field(default=30, ge=10, le=240)
    valid_from: date | None = None
    valid_until: date | None = None
    active: bool = True


class AvailabilityBlockPayload(BaseModel):
    doctor_id: str
    starts_at: datetime
    ends_at: datetime
    reason: str = "Bloqueio administrativo"


class StaffAppointmentPayload(BaseModel):
    patient_id: str
    doctor_id: str
    starts_at: datetime
    reason: str = "Consulta"


class IngestionReview(BaseModel):
    entities: list[dict] = Field(default_factory=list)
    confirmed: bool


class TextIngestionPayload(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    content: str = Field(min_length=2)


def staff(identity: dict = Depends(current_identity)) -> dict:
    require_staff(identity)
    return identity


def admin(identity: dict = Depends(current_identity)) -> dict:
    require_admin(identity)
    return identity


def audit(db: Session, identity: dict, action: str, resource_type: str, resource_id: str) -> None:
    db.add(AuditEvent(tenant_id=identity["tenant"], actor_id=identity["sub"], action=action, resource_type=resource_type, resource_id=resource_id))


def event_payload(payload: dict) -> dict:
    return {**payload, "_correlation_id": correlation_id()}


def catalog_model(kind: str):
    model = {"specialties": Specialty, "units": Unit, "insurers": Insurer, "exams": Exam}.get(kind)
    if not model:
        raise HTTPException(404, "Catálogo não encontrado")
    return model


def serialize_catalog(item) -> dict:
    fields = ("id", "name", "description", "address", "preparation", "unit_ids", "active")
    return {field: getattr(item, field) for field in fields if hasattr(item, field)}


@router.get("/dashboard")
def dashboard(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    tenant = identity["tenant"]
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    today_query = select(func.count()).select_from(Appointment).where(Appointment.tenant_id == tenant, Appointment.starts_at >= start, Appointment.starts_at < end)
    return {
        "appointments_today": db.scalar(today_query) or 0,
        "confirmed_today": db.scalar(today_query.where(Appointment.status == AppointmentStatus.confirmed)) or 0,
        "patients": db.scalar(select(func.count()).select_from(User).where(User.tenant_id == tenant, User.role == Role.patient, User.deleted_at.is_(None))) or 0,
        "knowledge_pending": db.scalar(select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.tenant_id == tenant, KnowledgeDocument.status == DocumentStatus.review_required)) or 0,
    }


@router.get("/agenda")
def agenda(
    start: date,
    end: date,
    doctor_id: str | None = None,
    unit_id: str | None = None,
    status: str | None = None,
    identity: dict = Depends(staff),
    db: Session = Depends(get_db),
):
    if (end - start).days > 31 or end < start:
        raise HTTPException(422, "Intervalo inválido")
    start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    query = select(Appointment).where(Appointment.tenant_id == identity["tenant"], Appointment.starts_at < end_at, Appointment.ends_at > start_at)
    if doctor_id:
        query = query.where(Appointment.doctor_id == doctor_id)
    if unit_id:
        query = query.where(Appointment.unit_id == unit_id)
    if status:
        query = query.where(Appointment.status == status)
    rows = db.scalars(query.order_by(Appointment.starts_at)).all()
    doctors = {item.id: item.name for item in db.scalars(select(Doctor).where(Doctor.tenant_id == identity["tenant"]))}
    patients = {item.id: item.name for item in db.scalars(select(User).where(User.tenant_id == identity["tenant"]))}
    units = {item.id: item.name for item in db.scalars(select(Unit).where(Unit.tenant_id == identity["tenant"]))}
    return {"items": [{"id": item.id, "doctor_id": item.doctor_id, "doctor": doctors.get(item.doctor_id), "patient_id": item.patient_id, "patient": patients.get(item.patient_id), "unit_id": item.unit_id, "unit": units.get(item.unit_id), "starts_at": item.starts_at, "ends_at": item.ends_at, "status": item.status.value, "reason": item.reason} for item in rows]}


def _slot_for_staff(db: Session, tenant: str, doctor_id: str, starts_at: datetime) -> dict:
    requested = starts_at if starts_at.tzinfo else starts_at.replace(tzinfo=timezone.utc)
    slots = available_slots(db, tenant, requested.date(), requested.date(), doctor_id=doctor_id)
    slot = next((item for item in slots if item["starts_at"] == requested), None)
    if not slot:
        raise HTTPException(409, "Horário indisponível")
    return slot


@router.post("/appointments", status_code=201)
def create_staff_appointment(payload: StaffAppointmentPayload, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    patient = db.scalar(select(User).where(User.id == payload.patient_id, User.tenant_id == identity["tenant"], User.role == Role.patient, User.deleted_at.is_(None)))
    if not patient:
        raise HTTPException(404, "Paciente não encontrado")
    slot = _slot_for_staff(db, identity["tenant"], payload.doctor_id, payload.starts_at)
    item = Appointment(tenant_id=identity["tenant"], patient_id=patient.id, doctor_id=payload.doctor_id, unit_id=slot["unit"]["id"], starts_at=slot["starts_at"], ends_at=slot["ends_at"], reason=payload.reason)
    db.add(item)
    try:
        db.flush()
        audit(db, identity, "appointment.created", "appointment", item.id)
        db.add(AppointmentHistory(tenant_id=identity["tenant"], appointment_id=item.id, actor_id=identity["sub"], from_status=None, to_status=AppointmentStatus.confirmed.value))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Horário já reservado") from exc
    return {"id": item.id}


@router.patch("/appointments/{appointment_id}")
def update_staff_appointment(appointment_id: str, payload: StaffAppointmentPayload, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    item = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Consulta não encontrada")
    original_status = item.status
    item.status = AppointmentStatus.cancelled
    db.flush()
    slot = _slot_for_staff(db, identity["tenant"], payload.doctor_id, payload.starts_at)
    item.patient_id = payload.patient_id
    item.doctor_id = payload.doctor_id
    item.unit_id = slot["unit"]["id"]
    item.starts_at = slot["starts_at"]
    item.ends_at = slot["ends_at"]
    item.reason = payload.reason
    item.status = AppointmentStatus.confirmed
    item.cancelled_at = None
    audit(db, identity, "appointment.rescheduled", "appointment", item.id)
    db.add(AppointmentHistory(tenant_id=identity["tenant"], appointment_id=item.id, actor_id=identity["sub"], from_status=original_status.value, to_status=AppointmentStatus.confirmed.value, reason="Reagendamento administrativo"))
    db.commit()
    return {"id": item.id}


@router.post("/appointments/{appointment_id}/cancel")
def cancel_staff_appointment(appointment_id: str, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    item = db.scalar(select(Appointment).where(Appointment.id == appointment_id, Appointment.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Consulta não encontrada")
    item.status = AppointmentStatus.cancelled
    item.cancelled_at = datetime.now(timezone.utc)
    audit(db, identity, "appointment.cancelled", "appointment", item.id)
    db.add(AppointmentHistory(tenant_id=identity["tenant"], appointment_id=item.id, actor_id=identity["sub"], from_status=AppointmentStatus.confirmed.value, to_status=AppointmentStatus.cancelled.value))
    db.commit()
    return {"id": item.id, "status": item.status.value}


@router.get("/doctors")
def doctors(q: str = "", include_inactive: bool = False, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    query = select(Doctor).where(Doctor.tenant_id == identity["tenant"], Doctor.deleted_at.is_(None))
    if q:
        query = query.where(or_(Doctor.name.ilike(f"%{q}%"), Doctor.crm.ilike(f"%{q}%")))
    if not include_inactive:
        query = query.where(Doctor.active.is_(True))
    rows = db.scalars(query.order_by(Doctor.name)).all()
    specialties = {item.id: item.name for item in db.scalars(select(Specialty).where(Specialty.tenant_id == identity["tenant"]))}
    units = {item.id: item.name for item in db.scalars(select(Unit).where(Unit.tenant_id == identity["tenant"]))}
    insurers = {item.id: item.name for item in db.scalars(select(Insurer).where(Insurer.tenant_id == identity["tenant"]))}
    return {"items": [{"id": item.id, "name": item.name, "crm": item.crm, "specialty_id": item.specialty_id, "specialty": specialties.get(item.specialty_id), "unit_id": item.unit_id, "unit": units.get(item.unit_id), "insurer_ids": item.insurer_ids, "insurers": [insurers.get(value) for value in item.insurer_ids if insurers.get(value)], "active": item.active} for item in rows]}


def validate_doctor_relations(payload: DoctorPayload, tenant: str, db: Session) -> None:
    if not db.scalar(select(Specialty.id).where(Specialty.id == payload.specialty_id, Specialty.tenant_id == tenant, Specialty.active.is_(True))):
        raise HTTPException(422, "Especialidade inválida")
    if not db.scalar(select(Unit.id).where(Unit.id == payload.unit_id, Unit.tenant_id == tenant, Unit.active.is_(True))):
        raise HTTPException(422, "Unidade inválida")
    count = db.scalar(select(func.count()).select_from(Insurer).where(Insurer.tenant_id == tenant, Insurer.id.in_(payload.insurer_ids), Insurer.active.is_(True))) or 0
    if count != len(set(payload.insurer_ids)):
        raise HTTPException(422, "Convênio inválido")


@router.post("/doctors", status_code=201)
def create_doctor(payload: DoctorPayload, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    validate_doctor_relations(payload, identity["tenant"], db)
    item = Doctor(tenant_id=identity["tenant"], **payload.model_dump())
    db.add(item)
    db.flush()
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type="doctor", aggregate_id=item.id, event_type="doctor.upserted", payload=event_payload({"id": item.id, **payload.model_dump()})))
    audit(db, identity, "doctor.created", "doctor", item.id)
    db.commit()
    return {"id": item.id, "sync_status": "pending"}


@router.put("/doctors/{doctor_id}")
def update_doctor(doctor_id: str, payload: DoctorPayload, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(Doctor).where(Doctor.id == doctor_id, Doctor.tenant_id == identity["tenant"], Doctor.deleted_at.is_(None)))
    if not item:
        raise HTTPException(404, "Médico não encontrado")
    validate_doctor_relations(payload, identity["tenant"], db)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type="doctor", aggregate_id=item.id, event_type="doctor.upserted", payload=event_payload({"id": item.id, **payload.model_dump()})))
    audit(db, identity, "doctor.updated", "doctor", item.id)
    db.commit()
    return {"id": item.id, "sync_status": "pending"}


@router.delete("/doctors/{doctor_id}", status_code=204)
def archive_doctor(doctor_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(Doctor).where(Doctor.id == doctor_id, Doctor.tenant_id == identity["tenant"], Doctor.deleted_at.is_(None)))
    if not item:
        raise HTTPException(404, "Médico não encontrado")
    item.active = False
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type="doctor", aggregate_id=item.id, event_type="doctor.deleted", payload=event_payload({"id": item.id})))
    audit(db, identity, "doctor.archived", "doctor", item.id)
    db.commit()
    return Response(status_code=204)


@router.get("/catalog/{kind}")
def list_catalog(kind: str, q: str = "", include_inactive: bool = False, page: int = 1, page_size: int = 50, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    model = catalog_model(kind)
    query = select(model).where(model.tenant_id == identity["tenant"])
    if q:
        query = query.where(model.name.ilike(f"%{q}%"))
    if not include_inactive:
        query = query.where(model.active.is_(True))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(model.name).offset((max(page, 1) - 1) * min(page_size, 100)).limit(min(page_size, 100))).all()
    return {"items": [serialize_catalog(item) for item in rows], "total": total, "page": page, "page_size": min(page_size, 100)}


def build_catalog(kind: str, payload: CatalogPayload, tenant: str):
    if kind == "specialties":
        return Specialty(tenant_id=tenant, name=payload.name, description=payload.description, active=payload.active)
    if kind == "units":
        return Unit(tenant_id=tenant, name=payload.name, address=payload.address, active=payload.active)
    if kind == "insurers":
        return Insurer(tenant_id=tenant, name=payload.name, active=payload.active)
    if kind == "exams":
        return Exam(tenant_id=tenant, name=payload.name, preparation=payload.preparation, unit_ids=payload.unit_ids, active=payload.active)
    raise HTTPException(404, "Catálogo não encontrado")


@router.post("/catalog/{kind}", status_code=201)
def create_catalog(kind: str, payload: CatalogPayload, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    catalog_model(kind)
    item = build_catalog(kind, payload, identity["tenant"])
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Já existe um registro com este nome") from exc
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type=kind, aggregate_id=item.id, event_type=f"{kind}.upserted", payload=event_payload(serialize_catalog(item))))
    audit(db, identity, f"{kind}.created", kind, item.id)
    db.commit()
    return {"id": item.id, "sync_status": "pending"}


@router.patch("/catalog/{kind}/{item_id}")
def update_catalog(kind: str, item_id: str, payload: CatalogPayload, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    model = catalog_model(kind)
    item = db.scalar(select(model).where(model.id == item_id, model.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Registro não encontrado")
    replacement = build_catalog(kind, payload, identity["tenant"])
    for field in ("name", "description", "address", "preparation", "unit_ids", "active"):
        if hasattr(item, field) and hasattr(replacement, field):
            setattr(item, field, getattr(replacement, field))
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type=kind, aggregate_id=item.id, event_type=f"{kind}.upserted", payload=event_payload(serialize_catalog(item))))
    audit(db, identity, f"{kind}.updated", kind, item.id)
    db.commit()
    return {"id": item.id, "sync_status": "pending"}


@router.delete("/catalog/{kind}/{item_id}", status_code=204)
def archive_catalog(kind: str, item_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    model = catalog_model(kind)
    item = db.scalar(select(model).where(model.id == item_id, model.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Registro não encontrado")
    item.active = False
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type=kind, aggregate_id=item.id, event_type=f"{kind}.deleted", payload=event_payload({"id": item.id})))
    audit(db, identity, f"{kind}.archived", kind, item.id)
    db.commit()
    return Response(status_code=204)


@router.get("/patients")
def patients(q: str = "", identity: dict = Depends(staff), db: Session = Depends(get_db)):
    query = select(User).where(User.tenant_id == identity["tenant"], User.role == Role.patient, User.deleted_at.is_(None))
    if q:
        query = query.where(or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    rows = db.scalars(query.order_by(User.name)).all()
    audit(db, identity, "patients.viewed", "patient", "collection")
    db.commit()
    return {"items": [{"id": item.id, "name": item.name, "email": item.email, "cpf": mask_cpf(item.cpf_encrypted), "birth_date": item.birth_date, "created_at": item.created_at} for item in rows]}


@router.get("/availability-rules")
def availability_rules(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(AvailabilityRule).where(AvailabilityRule.tenant_id == identity["tenant"]).order_by(AvailabilityRule.weekday, AvailabilityRule.starts_at)).all()
    return {"items": [{"id": item.id, "doctor_id": item.doctor_id, "unit_id": item.unit_id, "weekday": item.weekday, "starts_at": item.starts_at, "ends_at": item.ends_at, "slot_minutes": item.slot_minutes, "valid_from": item.valid_from, "valid_until": item.valid_until, "active": item.active} for item in rows]}


@router.post("/availability-rules", status_code=201)
def create_rule(payload: AvailabilityRulePayload, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    if payload.starts_at >= payload.ends_at:
        raise HTTPException(422, "Intervalo inválido")
    item = AvailabilityRule(tenant_id=identity["tenant"], **payload.model_dump())
    db.add(item)
    db.flush()
    audit(db, identity, "availability_rule.created", "availability_rule", item.id)
    db.commit()
    return {"id": item.id}


@router.patch("/availability-rules/{rule_id}")
def update_rule(rule_id: str, payload: AvailabilityRulePayload, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(AvailabilityRule).where(AvailabilityRule.id == rule_id, AvailabilityRule.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Regra não encontrada")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    audit(db, identity, "availability_rule.updated", "availability_rule", item.id)
    db.commit()
    return {"id": item.id}


@router.delete("/availability-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(AvailabilityRule).where(AvailabilityRule.id == rule_id, AvailabilityRule.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Regra não encontrada")
    item.active = False
    audit(db, identity, "availability_rule.archived", "availability_rule", item.id)
    db.commit()
    return Response(status_code=204)


@router.get("/availability-blocks")
def availability_blocks(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(AvailabilityBlock).where(AvailabilityBlock.tenant_id == identity["tenant"]).order_by(AvailabilityBlock.starts_at)).all()
    return {"items": [{"id": item.id, "doctor_id": item.doctor_id, "starts_at": item.starts_at, "ends_at": item.ends_at, "reason": item.reason} for item in rows]}


@router.post("/availability-blocks", status_code=201)
def create_block(payload: AvailabilityBlockPayload, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    if payload.starts_at >= payload.ends_at:
        raise HTTPException(422, "Intervalo inválido")
    item = AvailabilityBlock(tenant_id=identity["tenant"], **payload.model_dump())
    db.add(item)
    db.flush()
    audit(db, identity, "availability_block.created", "availability_block", item.id)
    db.commit()
    return {"id": item.id}


@router.delete("/availability-blocks/{block_id}", status_code=204)
def delete_block(block_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(AvailabilityBlock).where(AvailabilityBlock.id == block_id, AvailabilityBlock.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Bloqueio não encontrado")
    db.delete(item)
    audit(db, identity, "availability_block.deleted", "availability_block", item.id)
    db.commit()
    return Response(status_code=204)


@router.post("/ingestions/upload", status_code=202)
async def upload_ingestion(file: UploadFile = File(...), title: str = Form(...), identity: dict = Depends(admin), db: Session = Depends(get_db)):
    content = await file.read()
    if not content or len(content) > get_settings().upload_max_bytes:
        raise HTTPException(422, "Arquivo vazio ou acima do limite")
    if file.content_type not in {"application/pdf", "text/plain", "text/markdown", "image/png", "image/jpeg"}:
        raise HTTPException(415, "Formato não suportado")
    filename = file.filename or "documento"
    item = KnowledgeDocument(tenant_id=identity["tenant"], title=title, filename=filename, content_type=file.content_type or "application/octet-stream", source="Upload administrativo", status=DocumentStatus.uploaded)
    db.add(item)
    db.flush()
    item.storage_key = object_storage_provider().put_private(f"{identity['tenant']}/knowledge/{item.id}/{filename}", content, item.content_type)
    db.commit()
    if get_settings().app_env == "test":
        from worker.tasks import process_knowledge_document
        process_knowledge_document(item.id, identity["tenant"], correlation_id())
    else:
        from worker.celery_app import celery_app
        celery_app.send_task("worker.tasks.process_knowledge_document", args=[item.id, identity["tenant"], correlation_id()])
    audit(db, identity, "ingestion.uploaded", "knowledge_document", item.id)
    db.commit()
    return {"id": item.id, "status": item.status.value}


@router.post("/ingestions", status_code=201)
def create_text_ingestion(payload: TextIngestionPayload, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = KnowledgeDocument(
        tenant_id=identity["tenant"],
        title=payload.title,
        content=payload.content,
        filename=f"{payload.title}.txt",
        content_type="text/plain",
        source="Cadastro administrativo",
        status=DocumentStatus.review_required,
        chunks=[{"position": 0, "content": payload.content}],
    )
    db.add(item)
    db.flush()
    audit(db, identity, "ingestion.created", "knowledge_document", item.id)
    db.commit()
    return {"id": item.id, "status": item.status.value}


@router.get("/ingestions")
def ingestions(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == identity["tenant"]).order_by(KnowledgeDocument.created_at.desc())).all()
    pending = {item.aggregate_id for item in db.scalars(select(OutboxEvent).where(OutboxEvent.tenant_id == identity["tenant"], OutboxEvent.processed_at.is_(None)))}
    return {"items": [{"id": item.id, "title": item.title, "source": item.source, "status": item.status.value, "sync_status": "pending" if item.id in pending else "synced", "entities": item.entities, "preview": item.content[:500], "created_at": item.created_at} for item in rows]}


@router.post("/ingestions/{document_id}/approve")
def approve_ingestion(document_id: str, payload: IngestionReview, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    if not payload.confirmed:
        raise HTTPException(422, "Confirmação explícita é obrigatória")
    item = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Ingestão não encontrada")
    item.entities = payload.entities
    item.status = DocumentStatus.published
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type="knowledge_document", aggregate_id=item.id, event_type="knowledge.published", payload=event_payload({"id": item.id, "title": item.title, "source": item.source, "entities": item.entities, "chunks": item.chunks})))
    audit(db, identity, "ingestion.published", "knowledge_document", item.id)
    db.commit()
    return {"id": item.id, "status": item.status.value, "sync_status": "pending"}


@router.post("/ingestions/{document_id}/reject")
def reject_ingestion(document_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Ingestão não encontrada")
    item.status = DocumentStatus.rejected
    audit(db, identity, "ingestion.rejected", "knowledge_document", item.id)
    db.commit()
    return {"id": item.id, "status": item.status.value}
