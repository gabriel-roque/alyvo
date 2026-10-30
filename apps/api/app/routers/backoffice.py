from datetime import datetime

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
    Service,
    Specialty,
    Ticket,
    Unit,
    User,
)
from app.security import current_identity, require_admin, require_staff

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


class CatalogUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    address: str | None = None
    duration_minutes: int | None = None


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


@router.get("/dashboard")
def dashboard(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    tenant = identity["tenant"]
    return {
        "appointments": db.scalar(select(func.count()).select_from(Appointment).where(Appointment.tenant_id == tenant)),
        "patients": db.scalar(select(func.count()).select_from(User).where(User.tenant_id == tenant, User.role == "patient")),
        "documents_pending": db.scalar(select(func.count()).select_from(PatientDocument).where(PatientDocument.tenant_id == tenant, PatientDocument.confirmed.is_(False))),
        "tickets_open": db.scalar(select(func.count()).select_from(Ticket).where(Ticket.tenant_id == tenant, Ticket.status == "open")),
    }


@router.get("/agenda")
def agenda(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    appointments = db.scalars(select(Appointment).where(Appointment.tenant_id == identity["tenant"]).order_by(Appointment.starts_at)).all()
    doctors = {item.id: item.name for item in db.scalars(select(Doctor).where(Doctor.tenant_id == identity["tenant"]))}
    patients = {item.id: item.name for item in db.scalars(select(User).where(User.tenant_id == identity["tenant"]))}
    return {"items": [{"id": item.id, "doctor": doctors.get(item.doctor_id), "patient": patients.get(item.patient_id), "starts_at": item.starts_at, "ends_at": item.ends_at, "status": item.status.value} for item in appointments]}


@router.get("/doctors")
def doctors(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    return {"items": [{"id": item.id, "name": item.name, "crm": item.crm, "specialty_id": item.specialty_id, "unit_id": item.unit_id, "insurer_ids": item.insurer_ids} for item in db.scalars(select(Doctor).where(Doctor.tenant_id == identity["tenant"]))]}


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
    db.add(OutboxEvent(tenant_id=tenant, aggregate_type="doctor", aggregate_id=item.id, event_type="doctor.upserted", payload={"id": item.id, **payload.model_dump()}))
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
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type="doctor", aggregate_id=item.id, event_type="doctor.upserted", payload={"id": item.id, **payload.model_dump()}))
    db.commit()
    return {"id": item.id, "sync_status": "pending"}


@router.delete("/doctors/{doctor_id}", status_code=204)
def delete_doctor(doctor_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    from datetime import datetime, timezone

    item = db.scalar(select(Doctor).where(Doctor.id == doctor_id, Doctor.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Médico não encontrado")
    item.active = False
    item.deleted_at = datetime.now(timezone.utc)
    db.commit()


@router.get("/catalog/{kind}")
def list_catalog(kind: str, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    models = {"specialties": Specialty, "units": Unit, "insurers": Insurer, "exams": Exam, "services": Service}
    model = models.get(kind)
    if not model:
        raise HTTPException(404, "Catálogo não encontrado")
    rows = db.scalars(select(model).where(model.tenant_id == identity["tenant"])).all()
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
        item = Exam(tenant_id=identity["tenant"], name=fields["name"], preparation=fields["description"])
    elif kind == "services":
        item = Service(tenant_id=identity["tenant"], name=fields["name"])
    else:
        raise HTTPException(404, "Catálogo não encontrado")
    db.add(item)
    db.flush()
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type=kind, aggregate_id=item.id, event_type=f"{kind}.upserted", payload={"id": item.id, "name": item.name}))
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
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type=kind, aggregate_id=item.id, event_type=f"{kind}.upserted", payload={"id": item.id, "name": item.name}))
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
    db.commit()


@router.get("/patients")
def patients(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.tenant_id == identity["tenant"], User.role == "patient")).all()
    return {"items": [{"id": item.id, "name": item.name, "email": item.email} for item in rows]}


@router.get("/patient-documents")
def patient_documents(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(PatientDocument).where(PatientDocument.tenant_id == identity["tenant"], PatientDocument.deleted_at.is_(None))).all()
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
    db.commit()
    db.refresh(item)
    return {"id": item.id}


@router.delete("/availability-blocks/{block_id}", status_code=204)
def delete_availability_block(block_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(AvailabilityBlock).where(AvailabilityBlock.id == block_id, AvailabilityBlock.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Bloqueio não encontrado")
    db.delete(item)
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
    db.commit()
    return {"id": item.id, "status": item.status}


@router.post("/ingestions", status_code=201)
def create_ingestion(payload: IngestionCreate, identity: dict = Depends(staff), db: Session = Depends(get_db)):
    require_admin(identity)
    chunks = [payload.content[index : index + 700] for index in range(0, len(payload.content), 600)]
    item = KnowledgeDocument(tenant_id=identity["tenant"], title=payload.title, content=payload.content, source=payload.source, status=DocumentStatus.review_required, entities=[], chunks=chunks)
    db.add(item)
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

        process_knowledge_document(item.id, identity["tenant"])
    else:
        from worker.celery_app import celery_app

        celery_app.send_task(
            "worker.tasks.process_knowledge_document",
            args=[item.id, identity["tenant"]],
        )
    return {"id": item.id, "status": item.status.value}


@router.get("/ingestions")
def ingestions(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == identity["tenant"]).order_by(KnowledgeDocument.created_at.desc())).all()
    return {"items": [{"id": item.id, "title": item.title, "source": item.source, "status": item.status.value, "entities": item.entities, "preview": item.content[:240]} for item in rows]}


@router.post("/ingestions/{document_id}/approve")
def approve_ingestion(document_id: str, payload: IngestionReview, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    if not payload.confirmed:
        raise HTTPException(422, "Confirmação explícita é obrigatória")
    item = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Ingestão não encontrada")
    item.entities = payload.entities
    item.status = DocumentStatus.published
    db.add(OutboxEvent(tenant_id=identity["tenant"], aggregate_type="knowledge_document", aggregate_id=item.id, event_type="knowledge.published", payload={"id": item.id, "title": item.title, "source": item.source, "entities": item.entities, "chunks": item.chunks}))
    db.commit()
    return {"id": item.id, "status": item.status.value, "sync_status": "pending"}


@router.post("/ingestions/{document_id}/reject")
def reject_ingestion(document_id: str, identity: dict = Depends(admin), db: Session = Depends(get_db)):
    item = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.tenant_id == identity["tenant"]))
    if not item:
        raise HTTPException(404, "Ingestão não encontrada")
    item.status = DocumentStatus.rejected
    db.commit()
    return {"id": item.id, "status": item.status.value}


@router.get("/graph")
def graph(identity: dict = Depends(staff), db: Session = Depends(get_db)):
    if get_settings().app_env != "test":
        try:
            from neo4j import GraphDatabase

            settings = get_settings()
            driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
            with driver.session() as session:
                nodes = [dict(row["node"]) for row in session.run("MATCH (n {tenant_id: $tenant}) RETURN n {.*, type: head(labels(n))} AS node LIMIT 250", tenant=identity["tenant"])]
                edges = [dict(row["edge"]) for row in session.run("MATCH (a {tenant_id: $tenant})-[r]->(b {tenant_id: $tenant}) RETURN {source: a.id, target: b.id, type: type(r)} AS edge LIMIT 500", tenant=identity["tenant"])]
            driver.close()
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
    return {"items": [{"id": item.id, "actor_id": item.actor_id, "action": item.action, "resource_type": item.resource_type, "resource_id": item.resource_id, "metadata": item.metadata_json, "created_at": item.created_at} for item in rows]}

