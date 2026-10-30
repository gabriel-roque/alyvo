from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.providers import object_storage_provider
from app.config import get_settings
from app.db import get_db
from app.document_drafts import delete_draft, get_draft
from app.models import (
    Appointment,
    AppointmentHistory,
    AppointmentStatus,
    AuditEvent,
    Availability,
    AvailabilityBlock,
    Doctor,
    DocumentStatus,
    Insurer,
    PatientDocument,
    Specialty,
    Tenant,
    Unit,
)
from app.observability import correlation_id, record
from app.security import current_identity

router = APIRouter(tags=["operations"])


class DoctorView(BaseModel):
    id: str
    name: str
    crm: str
    specialty: str
    unit: str
    insurers: list[str]


class DoctorDirectoryResponse(BaseModel):
    items: list[DoctorView]


class SlotDoctor(BaseModel):
    id: str
    name: str
    crm: str


class SlotUnit(BaseModel):
    id: str
    name: str
    address: str


class AvailabilitySlot(BaseModel):
    id: str
    doctor: SlotDoctor
    unit: SlotUnit
    starts_at: datetime
    ends_at: datetime


class AvailabilityResponse(BaseModel):
    items: list[AvailabilitySlot]
    source: str


class AppointmentView(BaseModel):
    id: str
    doctor_id: str
    unit_id: str
    starts_at: datetime
    ends_at: datetime
    status: str
    reason: str


class DocumentView(BaseModel):
    id: str
    kind: str
    filename: str
    fields: dict[str, str]
    confidence: dict[str, float]
    confirmed: bool
    status: str
    created_at: datetime
    file_url: str | None = None


class AppointmentListResponse(BaseModel):
    items: list[AppointmentView]


class DocumentListResponse(BaseModel):
    items: list[DocumentView]


@router.get("/directory/doctors", response_model=DoctorDirectoryResponse)
def public_doctor_directory(tenant_id: str = "clinic-alyvo", db: Session = Depends(get_db)):
    rows = db.execute(
        select(Doctor, Specialty, Unit)
        .join(Specialty, Doctor.specialty_id == Specialty.id)
        .join(Unit, Doctor.unit_id == Unit.id)
        .where(Doctor.tenant_id == tenant_id, Doctor.active.is_(True), Doctor.deleted_at.is_(None))
        .order_by(Doctor.name)
    ).all()
    insurers = {item.id: item.name for item in db.scalars(select(Insurer).where(Insurer.tenant_id == tenant_id))}
    return {
        "items": [
            {
                "id": doctor.id,
                "name": doctor.name,
                "crm": doctor.crm,
                "specialty": specialty.name,
                "unit": unit.name,
                "insurers": [insurers[item] for item in doctor.insurer_ids if item in insurers],
            }
            for doctor, specialty, unit in rows
        ]
    }


class AppointmentCreate(BaseModel):
    doctor_id: str
    starts_at: datetime
    reason: str = "Consulta"
    confirmed: bool


class DocumentConfirm(BaseModel):
    fields: dict[str, str]
    confirmed: bool


def appointment_view(item: Appointment) -> dict:
    return {
        "id": item.id,
        "doctor_id": item.doctor_id,
        "unit_id": item.unit_id,
        "starts_at": item.starts_at,
        "ends_at": item.ends_at,
        "status": item.status.value,
        "reason": item.reason,
    }


@router.get("/availability", response_model=AvailabilityResponse)
def list_availability(
    day: date | None = None,
    doctor_id: str | None = None,
    specialty_id: str | None = None,
    unit_id: str | None = None,
    tenant_id: str = "clinic-alyvo",
    db: Session = Depends(get_db),
):
    query = (
        select(Availability, Doctor, Unit)
        .join(Doctor, Availability.doctor_id == Doctor.id)
        .join(Unit, Availability.unit_id == Unit.id)
        .where(Availability.tenant_id == tenant_id, Doctor.tenant_id == tenant_id, Unit.tenant_id == tenant_id)
    )
    if doctor_id:
        query = query.where(Availability.doctor_id == doctor_id)
    if specialty_id:
        query = query.where(Doctor.specialty_id == specialty_id)
    if unit_id:
        query = query.where(Availability.unit_id == unit_id)
    rows = db.execute(query.order_by(Availability.starts_at)).all()
    appointments = {
        (item.doctor_id, item.starts_at)
        for item in db.scalars(
            select(Appointment).where(Appointment.tenant_id == tenant_id, Appointment.status == AppointmentStatus.confirmed)
        )
    }
    blocks = db.scalars(select(AvailabilityBlock).where(AvailabilityBlock.tenant_id == tenant_id)).all()
    items = []
    for slot, doctor, unit in rows:
        slot_day = slot.starts_at.date()
        if day and slot_day != day:
            continue
        if (slot.doctor_id, slot.starts_at) in appointments:
            continue
        if any(block.doctor_id == slot.doctor_id and block.starts_at < slot.ends_at and block.ends_at > slot.starts_at for block in blocks):
            continue
        items.append(
            {
                "id": slot.id,
                "doctor": {"id": doctor.id, "name": doctor.name, "crm": doctor.crm},
                "unit": {"id": unit.id, "name": unit.name, "address": unit.address},
                "starts_at": slot.starts_at,
                "ends_at": slot.ends_at,
            }
        )
    return {"items": items, "source": "postgresql"}


@router.post("/appointments", status_code=201, response_model=AppointmentView)
def create_appointment(
    payload: AppointmentCreate,
    identity: dict = Depends(current_identity),
    db: Session = Depends(get_db),
):
    if identity["role"] != "patient":
        raise HTTPException(403, "Apenas pacientes podem agendar por este endpoint")
    if not payload.confirmed:
        raise HTTPException(422, "Confirmação explícita é obrigatória")
    slot = db.scalar(
        select(Availability)
        .where(
            Availability.tenant_id == identity["tenant"],
            Availability.doctor_id == payload.doctor_id,
            Availability.starts_at == payload.starts_at,
        )
        .with_for_update()
    )
    if not slot:
        raise HTTPException(404, "Horário não encontrado")
    conflict = db.scalar(
        select(Appointment).where(
            Appointment.tenant_id == identity["tenant"],
            Appointment.doctor_id == payload.doctor_id,
            Appointment.status == AppointmentStatus.confirmed,
            Appointment.starts_at < slot.ends_at,
            Appointment.ends_at > slot.starts_at,
        )
    )
    if conflict:
        raise HTTPException(409, "Horário já reservado")
    appointment = Appointment(
        tenant_id=identity["tenant"],
        patient_id=identity["sub"],
        doctor_id=payload.doctor_id,
        unit_id=slot.unit_id,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        reason=payload.reason,
    )
    db.add(appointment)
    try:
        db.flush()
        db.add(
            AuditEvent(
                tenant_id=identity["tenant"],
                actor_id=identity["sub"],
                action="appointment.created",
                resource_type="appointment",
                resource_id=appointment.id,
            )
        )
        db.add(
            AppointmentHistory(
                tenant_id=identity["tenant"],
                appointment_id=appointment.id,
                actor_id=identity["sub"],
                from_status=None,
                to_status=AppointmentStatus.confirmed.value,
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Horário já reservado") from exc
    db.refresh(appointment)
    return appointment_view(appointment)


@router.get("/appointments/me", response_model=AppointmentListResponse)
def my_appointments(identity: dict = Depends(current_identity), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Appointment).where(
            Appointment.tenant_id == identity["tenant"],
            Appointment.patient_id == identity["sub"],
        ).order_by(Appointment.starts_at)
    ).all()
    return {"items": [appointment_view(item) for item in rows]}


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentView)
def cancel_appointment(
    appointment_id: str,
    confirmed: bool = True,
    identity: dict = Depends(current_identity),
    db: Session = Depends(get_db),
):
    if not confirmed:
        raise HTTPException(422, "Confirmação explícita é obrigatória")
    item = db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.tenant_id == identity["tenant"],
            Appointment.patient_id == identity["sub"],
        )
    )
    if not item:
        raise HTTPException(404, "Agendamento não encontrado")
    policy = db.get(Tenant, identity["tenant"])
    notice = policy.cancellation_notice_hours if policy else 0
    starts_at = item.starts_at if item.starts_at.tzinfo else item.starts_at.replace(tzinfo=timezone.utc)
    if notice > 0 and datetime.now(timezone.utc) > starts_at - timedelta(hours=notice):
        raise HTTPException(409, f"Cancelamentos exigem antecedência de {notice} horas")
    item.status = AppointmentStatus.cancelled
    item.cancelled_at = datetime.now(timezone.utc)
    db.add(AuditEvent(tenant_id=identity["tenant"], actor_id=identity["sub"], action="appointment.cancelled", resource_type="appointment", resource_id=item.id))
    db.add(AppointmentHistory(tenant_id=identity["tenant"], appointment_id=item.id, actor_id=identity["sub"], from_status=AppointmentStatus.confirmed.value, to_status=AppointmentStatus.cancelled.value))
    db.commit()
    return appointment_view(item)


def document_view(item: PatientDocument, include_draft: bool = False) -> dict:
    draft = get_draft(item.tenant_id, item.patient_id, item.id) if include_draft and not item.confirmed else {}
    return {
        "id": item.id,
        "kind": item.kind,
        "filename": item.filename,
        "fields": draft.get("fields", item.fields),
        "confidence": draft.get("confidence", item.confidence),
        "confirmed": item.confirmed,
        "status": item.status.value,
        "created_at": item.created_at,
        "file_url": object_storage_provider().presigned_get(item.storage_key) if item.storage_key else None,
    }


@router.post("/patient/documents", status_code=202, response_model=DocumentView)
async def upload_patient_document(
    file: UploadFile = File(...),
    kind: str = Form("insurance_card"),
    identity: dict = Depends(current_identity),
    db: Session = Depends(get_db),
):
    if identity["role"] != "patient":
        raise HTTPException(403, "Apenas pacientes podem enviar documentos")
    content = await file.read()
    if not content or len(content) > get_settings().upload_max_bytes:
        raise HTTPException(422, "Arquivo vazio ou maior que 10 MB")
    allowed = {"image/png", "image/jpeg", "application/pdf"}
    if file.content_type not in allowed:
        raise HTTPException(415, "Formato não suportado")
    provisional_key = f"{identity['tenant']}/patients/{identity['sub']}/{file.filename}"
    signatures = {
        "image/png": content.startswith(b"\x89PNG"),
        "image/jpeg": content.startswith(b"\xff\xd8"),
        "application/pdf": content.startswith(b"%PDF"),
    }
    if not signatures.get(file.content_type, False):
        raise HTTPException(415, "Conteúdo do arquivo não corresponde ao formato informado")
    storage_key = object_storage_provider().put_private(provisional_key, content, file.content_type or "application/octet-stream")
    item = PatientDocument(
        tenant_id=identity["tenant"],
        patient_id=identity["sub"],
        kind=kind,
        filename=file.filename or "documento",
        storage_key=storage_key,
        raw_ocr="",
        fields={},
        confidence={},
        status=DocumentStatus.uploaded,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    if get_settings().app_env == "test":
        from worker.tasks import process_patient_document

        process_patient_document(item.id, identity["tenant"], correlation_id())
        db.refresh(item)
    else:
        from worker.celery_app import celery_app

        celery_app.send_task(
            "worker.tasks.process_patient_document",
            args=[item.id, identity["tenant"], correlation_id()],
        )
    record("patient_document.uploaded", document_id=item.id, kind=kind)
    return document_view(item, include_draft=True)


@router.get("/patient/documents", response_model=DocumentListResponse)
def list_patient_documents(identity: dict = Depends(current_identity), db: Session = Depends(get_db)):
    items = db.scalars(select(PatientDocument).where(PatientDocument.tenant_id == identity["tenant"], PatientDocument.patient_id == identity["sub"], PatientDocument.deleted_at.is_(None))).all()
    return {"items": [document_view(item, include_draft=True) for item in items]}


@router.get("/patient/documents/{document_id}", response_model=DocumentView)
def get_patient_document(document_id: str, identity: dict = Depends(current_identity), db: Session = Depends(get_db)):
    item = db.scalar(select(PatientDocument).where(PatientDocument.id == document_id, PatientDocument.tenant_id == identity["tenant"], PatientDocument.patient_id == identity["sub"], PatientDocument.deleted_at.is_(None)))
    if not item:
        raise HTTPException(404, "Documento não encontrado")
    return document_view(item, include_draft=True)


@router.post("/patient/documents/{document_id}/confirm", response_model=DocumentView)
def confirm_patient_document(
    document_id: str,
    payload: DocumentConfirm,
    identity: dict = Depends(current_identity),
    db: Session = Depends(get_db),
):
    item = db.scalar(select(PatientDocument).where(PatientDocument.id == document_id, PatientDocument.tenant_id == identity["tenant"], PatientDocument.patient_id == identity["sub"], PatientDocument.deleted_at.is_(None)))
    if not item:
        raise HTTPException(404, "Documento não encontrado")
    if not payload.confirmed:
        raise HTTPException(422, "Confirmação explícita é obrigatória")
    draft = get_draft(identity["tenant"], identity["sub"], item.id)
    item.fields = payload.fields
    item.confidence = draft.get("confidence", {})
    item.raw_ocr = draft.get("raw_ocr", "")
    item.confirmed = True
    item.status = DocumentStatus.approved
    item.confirmed_by = identity["sub"]
    item.confirmed_at = datetime.now(timezone.utc)
    db.add(AuditEvent(tenant_id=identity["tenant"], actor_id=identity["sub"], action="patient_document.confirmed", resource_type="patient_document", resource_id=item.id, metadata_json={"fields": sorted(payload.fields)}))
    db.commit()
    delete_draft(identity["tenant"], identity["sub"], item.id)
    record("patient_document.confirmed", document_id=item.id, field_names=sorted(payload.fields))
    return document_view(item)

