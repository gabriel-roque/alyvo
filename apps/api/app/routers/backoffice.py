from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.providers import object_storage_provider
from app.config import get_settings
from app.db import get_db
from app.models import (
    Appointment,
    AuditEvent,
    AvailabilityBlock,
    Doctor,
    DocumentStatus,
    Exam,
    Insurer,
    KnowledgeDocument,
    OutboxEvent,
    PatientDocument,
    Role,
    Service,
    Specialty,
    Tenant,
    Ticket,
    Unit,
    User,
)
from app.observability import correlation_id
from app.security import current_identity, hash_password, require_admin, require_staff

router = APIRouter(prefix="/backoffice", tags=["backoffice"])


class DoctorCreate(BaseModel):
    name: str
    crm: str
    specialty_id: str
    unit_id: str
    insurer_ids: list[str] = []


class CatalogCreate(BaseModel):
    name: str
    description: str = ""
    address: str = ""
    duration_minutes: int = 30
    specialty_id: str | None = None
    unit_ids: list[str] = []


class CatalogUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    address: str | None = None
    duration_minutes: int | None = None
    specialty_id: str | None = None
    unit_ids: list[str] | None = None


class ClinicUpdate(BaseModel):
    name: str
    timezone: str = "America/Sao_Paulo"
    cancellation_notice_hours: int = 0


class StaffUserCreate(BaseModel):
    name: str
    email: str
    role: Role
    password: str


class StaffUserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role: Role | None = None
    password: str | None = None


class TicketUpdate(BaseModel):
    status: str


class AvailabilityBlockCreate(BaseModel):
    doctor_id: str
    starts_at: datetime
    ends_at: datetime
    reason: str = "Bloqueio administrativo"


class IngestionCreate(BaseModel):
    title: str
    content: str
    source: str = "Upload administrativo"


class IngestionReview(BaseModel):
    entities: list[dict] = []
    confirmed: bool


def staff(identity: dict = Depends(current_identity)) -> dict:
    require_staff(identity)
    return identity


def admin(identity: dict = Depends(current_identity)) -> dict:
    require_admin(identity)
    return identity


def add_audit(db: Session, identity: dict, action: str, resource_type: str, resource_id: str, metadata: dict | None = None) -> None:
    db.add(AuditEvent(tenant_id=identity["tenant"], actor_id=identity["sub"], action=action, resource_type=resource_type, resource_id=resource_id, metadata_json=metadata or {}))


def catalog_payload(item) -> dict:
    allowed = {"id", "name", "description", "address", "preparation", "unit_ids", "duration_minutes", "specialty_id", "active"}
    return {column.name: getattr(item, column.name) for column in item.__table__.columns if column.name in allowed}


def event_payload(payload: dict) -> dict:
    return {**payload, "_correlation_id": correlation_id()}


@router.get("/dashboard")
def dashboard(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    tenant = identity["tenant"]
    return {
        "appointments": db.scalar(select(func.count()).select_from(Appointment).where(Appointment.tenant_id == tenant)),
        "patients": db.scalar(select(func.count()).select_from(User).where(User.tenant_id == tenant, User.role == "patient", User.deleted_at.is_(None))),
        "documents_pending": db.scalar(select(func.count()).select_from(PatientDocument).where(PatientDocument.tenant_id == tenant, PatientDocument.confirmed.is_(False))),
        "tickets_open": db.scalar(select(func.count()).select_from(Ticket).where(Ticket.tenant_id == tenant, Ticket.status == "open")),
    }


@router.get("/agenda")
def agenda(day: date | None = None, doctor_id: str | None = None, unit_id: str | None = None, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    query = select(Appointment).where(Appointment.tenant_id == identity["tenant"])
    if doctor_id:
        query = query.where(Appointment.doctor_id == doctor_id)
    if unit_id:
        query = query.where(Appointment.unit_id == unit_id)
    appointments = db.scalars(query.order_by(Appointment.starts_at)).all()
    if day:
        appointments = [item for item in appointments if item.starts_at.date() == day]
    doctors = {item.id: item.name for item in db.scalars(select(Doctor).where(Doctor.tenant_id == identity["tenant"], Doctor.deleted_at.is_(None)))}
    patients = {item.id: item.name for item in db.scalars(select(User).where(User.tenant_id == identity["tenant"], User.deleted_at.is_(None)))}
    return {"items": [{"id": item.id, "doctor": doctors.get(item.doctor_id), "patient": patients.get(item.patient_id), "starts_at": item.starts_at, "ends_at": item.ends_at, "status": item.status.value} for item in appointments]}


@router.get("/doctors")
def doctors(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    return {"items": [{"id": item.id, "name": item.name, "crm": item.crm, "specialty_id": item.specialty_id, "unit_id": item.unit_id, "insurer_ids": item.insurer_ids} for item in db.scalars(select(Doctor).where(Doctor.tenant_id == identity["tenant"], Doctor.deleted_at.is_(None)))]}


@router.post("/doctors", status_code=201)
def create_doctor(payload: DoctorCreate, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    tenant = identity["tenant"]
    specialty = db.scalar(select(Specialty).where(Specialty.id == payload.specialty_id, Specialty.tenant_id == tenant))
    unit = db.scalar(select(Unit).where(Unit.id == payload.unit_id, Unit.tenant_id == tenant))
    insurer_count = db.scalar(select(func.count()).select_from(Insurer).where(Insurer.tenant_id == tenant, Insurer.id.in_(payload.insurer_ids)))
    if not specialty or not unit or insurer_count != len(set(payload.insurer_ids)):
        raise HTTPException(422, "Relacionamentos inválidos para esta clínica")
    item = Doctor(tenant_id=tenant, **payload.model_dump())
    db.add(item)
    db.flush()
    db.add(OutboxEvent(tenant_id=tenant, aggregate_type="doctor", aggregate_id=item.id, event_type="doctor.upserted", payload=event_payload({"id": item.id, **payload.model_dump()})))
    add_audit(db, identity, "doctor.created", "doctor", item.id)
    db.commit()
    return {"id": item.id, "sync_status": "pending"}


@router.put("/doctors/{doctor_id}")
def update_doctor(doctor_id: str, payload: DoctorCreate, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(Doctor).where(Doctor.id == doctor_id, Doctor.tenant_id == identity["tenant"], Doctor.deleted_at.is_(None)))
    if not item:
        raise HTTPException(404, "Médico não encontrado")
    specialty = db.scalar(select(Specialty).where(Specialty.id == payload.specialty_id, Specialty.tenant_id == identity["tenant"]))
    unit = db.scalar(select(Unit).where(Unit.id == payload.unit_id, Unit.tenant_id == identity["tenant"]))
    insurer_count = db.scalar(select(func.count()).select_from(Insurer).where(Insurer.tenant_id == identity["tenant"], Insurer.id.in_(payload.insurer_ids)))
    if not specialty or not unit or insurer_count != len(set(payload.insurer_ids)):
        raise HTTPException(422, "Relacionamentos inválidos para esta clínica")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type="doctor", aggregate_id=item.id, event_type="doctor.upserted", payload=event_payload({"id": item.id, **payload.model_dump()})))
    add_audit(db, identity, "doctor.updated", "doctor", item.id)
    db.commit()
    return {"id": item.id, "sync_status": "pending"}


@router.delete("/doctors/{doctor_id}", status_code=204)
def delete_doctor(doctor_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    from datetime import datetime, timezone

    item = db.scalar(select(Doctor).where(Doctor.id == doctor_id, Doctor.tenant_id == identity["tenant"], Doctor.deleted_at.is_(None)))
    if not item:
        raise HTTPException(404, "Médico não encontrado")
    item.active = False
    item.deleted_at = datetime.now(timezone.utc)
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type="doctor", aggregate_id=item.id, event_type="doctor.deleted", payload=event_payload({"id": item.id})))
    add_audit(db, identity, "doctor.deleted", "doctor", item.id)
    db.commit()


@router.get("/catalog/{kind}")
def list_catalog(kind: str, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    models = {"specialties": Specialty, "units": Unit, "insurers": Insurer, "exams": Exam, "services": Service}
    model = models.get(kind)
    if not model:
        raise HTTPException(404, "Catálogo não encontrado")
    rows = db.scalars(select(model).where(model.tenant_id == identity["tenant"])).all()
    if hasattr(model, "active"):
        rows = [item for item in rows if item.active]
    return {"items": [{column.name: getattr(item, column.name) for column in model.__table__.columns if column.name not in {"tenant_id"}} for item in rows]}


@router.post("/catalog/{kind}", status_code=201)
def create_catalog(kind: str, payload: CatalogCreate, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    fields = payload.model_dump()
    if kind == "specialties":
        item = Specialty(tenant_id=identity["tenant"], name=fields["name"], description=fields["description"])
    elif kind == "units":
        item = Unit(tenant_id=identity["tenant"], name=fields["name"], address=fields["address"])
    elif kind == "insurers":
        item = Insurer(tenant_id=identity["tenant"], name=fields["name"])
    elif kind == "exams":
        item = Exam(tenant_id=identity["tenant"], name=fields["name"], preparation=fields["description"], unit_ids=fields["unit_ids"])
    elif kind == "services":
        item = Service(tenant_id=identity["tenant"], name=fields["name"], duration_minutes=fields["duration_minutes"], specialty_id=fields["specialty_id"])
    else:
        raise HTTPException(404, "Catálogo não encontrado")
    db.add(item)
    db.flush()
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type=kind, aggregate_id=item.id, event_type=f"{kind}.upserted", payload=event_payload(catalog_payload(item))))
    add_audit(db, identity, f"{kind}.created", kind, item.id)
    db.commit()
    return {"id": item.id, "sync_status": "pending"}


@router.patch("/catalog/{kind}/{item_id}")
def update_catalog(kind: str, item_id: str, payload: CatalogUpdate, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    models = {"specialties": Specialty, "units": Unit, "insurers": Insurer, "exams": Exam, "services": Service}
    model = models.get(kind)
    if not model:
        raise HTTPException(404, "Catálogo não encontrado")
    item = db.scalar(select(model).where(model.id == item_id, model.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Item não encontrado")
    for key, value in payload.model_dump(exclude_none=True).items():
        if hasattr(item, key):
            setattr(item, key, value)
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type=kind, aggregate_id=item.id, event_type=f"{kind}.upserted", payload=event_payload(catalog_payload(item))))
    add_audit(db, identity, f"{kind}.updated", kind, item.id)
    db.commit()
    return {"id": item.id, "sync_status": "pending"}


@router.delete("/catalog/{kind}/{item_id}", status_code=204)
def delete_catalog(kind: str, item_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    models = {"specialties": Specialty, "units": Unit, "insurers": Insurer, "exams": Exam, "services": Service}
    model = models.get(kind)
    if not model:
        raise HTTPException(404, "Catálogo não encontrado")
    item = db.scalar(select(model).where(model.id == item_id, model.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Item não encontrado")
    if hasattr(item, "active"):
        item.active = False
    else:
        db.delete(item)
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type=kind, aggregate_id=item.id, event_type=f"{kind}.deleted", payload=event_payload({"id": item.id})))
    add_audit(db, identity, f"{kind}.deleted", kind, item.id)
    db.commit()


@router.get("/patients")
def patients(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.tenant_id == identity["tenant"], User.role == "patient", User.deleted_at.is_(None))).all()
    add_audit(db, identity, "patients.viewed", "patient", "collection", {"count": len(rows)})
    db.commit()
    return {"items": [{"id": item.id, "name": item.name, "email": item.email} for item in rows]}


@router.get("/patient-documents")
def patient_documents(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(PatientDocument).where(PatientDocument.tenant_id == identity["tenant"], PatientDocument.deleted_at.is_(None), PatientDocument.confirmed.is_(True))).all()
    db.add(AuditEvent(tenant_id=identity["tenant"], actor_id=identity["sub"], action="patient_documents.viewed", resource_type="patient_document", resource_id="collection", metadata_json={"count": len(rows)}))
    db.commit()
    return {"items": [{"id": item.id, "patient_id": item.patient_id, "kind": item.kind, "filename": item.filename, "fields": item.fields, "confirmed": item.confirmed, "status": item.status.value} for item in rows]}


@router.get("/availability-blocks")
def availability_blocks(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(AvailabilityBlock).where(AvailabilityBlock.tenant_id == identity["tenant"]).order_by(AvailabilityBlock.starts_at)).all()
    return {"items": [{"id": item.id, "doctor_id": item.doctor_id, "starts_at": item.starts_at, "ends_at": item.ends_at, "reason": item.reason} for item in rows]}


@router.post("/availability-blocks", status_code=201)
def create_availability_block(payload: AvailabilityBlockCreate, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    if payload.starts_at >= payload.ends_at:
        raise HTTPException(422, "Intervalo inválido")
    doctor = db.scalar(select(Doctor).where(Doctor.id == payload.doctor_id, Doctor.tenant_id == identity["tenant"], Doctor.active.is_(True)))
    if not doctor:
        raise HTTPException(404, "Médico não encontrado")
    item = AvailabilityBlock(tenant_id=identity["tenant"], **payload.model_dump())
    db.add(item)
    db.flush()
    add_audit(db, identity, "availability_block.created", "availability_block", item.id)
    db.commit()
    db.refresh(item)
    return {"id": item.id}


@router.delete("/availability-blocks/{block_id}", status_code=204)
def delete_availability_block(block_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(AvailabilityBlock).where(AvailabilityBlock.id == block_id, AvailabilityBlock.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Bloqueio não encontrado")
    db.delete(item)
    add_audit(db, identity, "availability_block.deleted", "availability_block", item.id)
    db.commit()
    return Response(status_code=204)


@router.get("/tickets")
def tickets(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(Ticket).where(Ticket.tenant_id == identity["tenant"]).order_by(Ticket.created_at.desc())).all()
    return {"items": [{"id": item.id, "subject": item.subject, "message": item.message, "status": item.status, "created_at": item.created_at} for item in rows]}


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: str, payload: TicketUpdate, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    item = db.scalar(select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Ticket não encontrado")
    if payload.status not in {"open", "in_progress", "resolved"}:
        raise HTTPException(422, "Status inválido")
    item.status = payload.status
    add_audit(db, identity, "ticket.updated", "ticket", item.id, {"status": payload.status})
    db.commit()
    return {"id": item.id, "status": item.status}


@router.post("/ingestions", status_code=201)
def create_ingestion(payload: IngestionCreate, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    require_admin(identity)
    chunks = [payload.content[index : index + 700] for index in range(0, len(payload.content), 600)]
    item = KnowledgeDocument(tenant_id=identity["tenant"], title=payload.title, content=payload.content, source=payload.source, status=DocumentStatus.review_required, entities=[], chunks=chunks)
    db.add(item)
    db.flush()
    add_audit(db, identity, "ingestion.created", "knowledge_document", item.id)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "status": item.status.value, "preview": item.content[:500]}


@router.post("/ingestions/upload", status_code=202)
async def upload_ingestion(
    file: UploadFile = File(...),
    title: str = Form(...),
    identity: dict = Depends(admin),
    db: Session = Depends(get_db),
):
    content = await file.read()
    if not content or len(content) > get_settings().upload_max_bytes:
        raise HTTPException(422, "Arquivo vazio ou acima do limite")
    allowed = {"application/pdf", "text/plain", "text/markdown", "image/png", "image/jpeg"}
    if file.content_type not in allowed:
        raise HTTPException(415, "Formato não suportado")
    filename = file.filename or "documento"
    item = KnowledgeDocument(
        tenant_id=identity["tenant"],
        title=title,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        source="Upload administrativo",
        status=DocumentStatus.uploaded,
    )
    db.add(item)
    db.flush()
    key = f"{identity['tenant']}/knowledge/{item.id}/{filename}"
    item.storage_key = object_storage_provider().put_private(key, content, item.content_type)
    db.commit()
    if get_settings().app_env == "test":
        from worker.tasks import process_knowledge_document

        process_knowledge_document(item.id, identity["tenant"], correlation_id())
    else:
        from worker.celery_app import celery_app

        celery_app.send_task(
            "worker.tasks.process_knowledge_document",
            args=[item.id, identity["tenant"], correlation_id()],
        )
    add_audit(db, identity, "ingestion.uploaded", "knowledge_document", item.id)
    db.commit()
    return {"id": item.id, "status": item.status.value}


@router.get("/ingestions")
def ingestions(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == identity["tenant"]).order_by(KnowledgeDocument.created_at.desc())).all()
    pending = {item.aggregate_id for item in db.scalars(select(OutboxEvent).where(OutboxEvent.tenant_id == identity["tenant"], OutboxEvent.processed_at.is_(None)))}
    return {"items": [{"id": item.id, "title": item.title, "source": item.source, "status": item.status.value, "sync_status": "pending" if item.id in pending else "synced", "entities": item.entities, "preview": item.content[:240]} for item in rows]}


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
    add_audit(db, identity, "ingestion.published", "knowledge_document", item.id)
    db.commit()
    return {"id": item.id, "status": item.status.value, "sync_status": "pending"}


@router.post("/ingestions/{document_id}/reject")
def reject_ingestion(document_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Ingestão não encontrada")
    item.status = DocumentStatus.rejected
    add_audit(db, identity, "ingestion.rejected", "knowledge_document", item.id)
    db.commit()
    return {"id": item.id, "status": item.status.value}


@router.get("/graph")
def graph(entity_type: str | None = None, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    if get_settings().app_env != "test":
        try:
            from neo4j import GraphDatabase

            settings = get_settings()
            driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
            with driver.session() as session:
                nodes = [dict(row["node"]) for row in session.run("MATCH (n {tenant_id: $tenant}) WHERE $entity_type IS NULL OR $entity_type IN labels(n) RETURN n {.*, type: head(labels(n))} AS node LIMIT 250", tenant=identity["tenant"], entity_type=entity_type)]
                edges = [dict(row["edge"]) for row in session.run("MATCH (a {tenant_id: $tenant})-[r]->(b {tenant_id: $tenant}) RETURN {source: a.id, target: b.id, type: type(r)} AS edge LIMIT 500", tenant=identity["tenant"])]
            driver.close()
            add_audit(db, identity, "graph.viewed", "graph", "collection", {"entity_type": entity_type})
            db.commit()
            return {"nodes": nodes, "edges": edges, "readonly": True, "source": "neo4j"}
        except Exception:
            pass
    doctors = db.scalars(select(Doctor).where(Doctor.tenant_id == identity["tenant"])).all()
    specialties = {item.id: item for item in db.scalars(select(Specialty).where(Specialty.tenant_id == identity["tenant"]))}
    units = {item.id: item for item in db.scalars(select(Unit).where(Unit.tenant_id == identity["tenant"]))}
    nodes = []
    edges = []
    for doctor in doctors:
        nodes.extend([{"id": doctor.id, "label": doctor.name, "type": "Doctor"}, {"id": doctor.specialty_id, "label": specialties[doctor.specialty_id].name, "type": "Specialty"}, {"id": doctor.unit_id, "label": units[doctor.unit_id].name, "type": "Unit"}])
        edges.extend([{"source": doctor.id, "target": doctor.specialty_id, "type": "HAS_SPECIALTY"}, {"source": doctor.id, "target": doctor.unit_id, "type": "WORKS_AT"}])
    return {"nodes": list({item["id"]: item for item in nodes}.values()), "edges": edges, "readonly": True, "source": "postgresql-fallback"}


@router.get("/audit")
def audit(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == identity["tenant"]).order_by(AuditEvent.created_at.desc())).all()
    add_audit(db, identity, "audit.viewed", "audit_event", "collection", {"count": len(rows)})
    db.commit()
    return {"items": [{"id": item.id, "actor_id": item.actor_id, "action": item.action, "resource_type": item.resource_type, "resource_id": item.resource_id, "metadata": item.metadata_json, "created_at": item.created_at} for item in rows]}


@router.get("/clinic")
def clinic(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    item = db.get(Tenant, identity["tenant"])
    return {"id": item.id, "name": item.name, "timezone": item.timezone, "cancellation_notice_hours": item.cancellation_notice_hours}


@router.patch("/clinic")
def update_clinic(payload: ClinicUpdate, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.get(Tenant, identity["tenant"])
    item.name = payload.name
    item.timezone = payload.timezone
    item.cancellation_notice_hours = payload.cancellation_notice_hours
    add_audit(db, identity, "clinic.updated", "clinic", item.id)
    db.commit()
    return {"id": item.id, "name": item.name, "timezone": item.timezone, "cancellation_notice_hours": item.cancellation_notice_hours}


@router.get("/users")
def staff_users(identity: dict = Depends(admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.tenant_id == identity["tenant"], User.role.in_([Role.admin, Role.receptionist]), User.deleted_at.is_(None))).all()
    return {"items": [{"id": item.id, "name": item.name, "email": item.email, "role": item.role.value} for item in rows]}


@router.post("/users", status_code=201)
def create_staff_user(payload: StaffUserCreate, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    if payload.role not in {Role.admin, Role.receptionist}:
        raise HTTPException(422, "Perfil inválido para usuário interno")
    item = User(tenant_id=identity["tenant"], name=payload.name, email=payload.email, role=payload.role, password_hash=hash_password(payload.password))
    db.add(item)
    db.flush()
    add_audit(db, identity, "staff_user.created", "user", item.id, {"role": payload.role.value})
    db.commit()
    return {"id": item.id}


@router.patch("/users/{user_id}")
def update_staff_user(user_id: str, payload: StaffUserUpdate, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(User).where(User.id == user_id, User.tenant_id == identity["tenant"], User.role.in_([Role.admin, Role.receptionist]), User.deleted_at.is_(None)))
    if not item:
        raise HTTPException(404, "Usuário não encontrado")
    values = payload.model_dump(exclude_none=True)
    if "role" in values and values["role"] not in {Role.admin, Role.receptionist}:
        raise HTTPException(422, "Perfil inválido")
    password = values.pop("password", None)
    for key, value in values.items():
        setattr(item, key, value)
    if password:
        item.password_hash = hash_password(password)
    add_audit(db, identity, "staff_user.updated", "user", item.id)
    db.commit()
    return {"id": item.id}


@router.delete("/users/{user_id}", status_code=204)
def delete_staff_user(user_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(User).where(User.id == user_id, User.tenant_id == identity["tenant"], User.role.in_([Role.admin, Role.receptionist]), User.deleted_at.is_(None)))
    if not item:
        raise HTTPException(404, "Usuário não encontrado")
    if item.id == identity["sub"]:
        raise HTTPException(409, "Não é possível remover o próprio usuário")
    from datetime import timezone
    item.deleted_at = datetime.now(timezone.utc)
    add_audit(db, identity, "staff_user.deleted", "user", item.id)
    db.commit()
    return Response(status_code=204)

