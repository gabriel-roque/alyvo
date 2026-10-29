from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.providers import LocalObjectStorage, ocr_provider
from app.db import get_db
from app.models import (
    Appointment,
    AppointmentStatus,
    AuditEvent,
    Availability,
    Doctor,
    DocumentStatus,
    PatientDocument,
    Unit,
)
from app.security import current_identity

router = APIRouter(tags=["operations"])


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


@router.get("/availability")
def list_availability(
    day: date | None = None,
    doctor_id: str | None = None,
    specialty_id: str | None = None,
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
    rows = db.execute(query.order_by(Availability.starts_at)).all()
    appointments = {
        (item.doctor_id, item.starts_at)
        for item in db.scalars(
            select(Appointment).where(Appointment.tenant_id == tenant_id, Appointment.status == AppointmentStatus.confirmed)
        )
    }
    items = []
    for slot, doctor, unit in rows:
        slot_day = slot.starts_at.date()
        if day and slot_day != day:
            continue
        if (slot.doctor_id, slot.starts_at) in appointments:
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


@router.post("/appointments", status_code=201)
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
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Horário já reservado") from exc
    db.refresh(appointment)
    return appointment_view(appointment)


@router.get("/appointments/me")
def my_appointments(identity: dict = Depends(current_identity), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Appointment).where(
            Appointment.tenant_id == identity["tenant"],
            Appointment.patient_id == identity["sub"],
        ).order_by(Appointment.starts_at)
    ).all()
    return {"items": [appointment_view(item) for item in rows]}


@router.post("/appointments/{appointment_id}/cancel")
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
    item.status = AppointmentStatus.cancelled
    item.cancelled_at = datetime.now(timezone.utc)
    db.add(AuditEvent(tenant_id=identity["tenant"], actor_id=identity["sub"], action="appointment.cancelled", resource_type="appointment", resource_id=item.id))
    db.commit()
    return appointment_view(item)


def document_view(item: PatientDocument) -> dict:
    return {
        "id": item.id,
        "kind": item.kind,
        "filename": item.filename,
        "fields": item.fields,
        "confidence": item.confidence,
        "confirmed": item.confirmed,
        "status": item.status.value,
        "created_at": item.created_at,
    }


@router.post("/patient/documents", status_code=202)
async def upload_patient_document(
    file: UploadFile = File(...),
    kind: str = Form("insurance_card"),
    identity: dict = Depends(current_identity),
    db: Session = Depends(get_db),
):
    if identity["role"] != "patient":
        raise HTTPException(403, "Apenas pacientes podem enviar documentos")
    content = await file.read()
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(422, "Arquivo vazio ou maior que 10 MB")
    allowed = {"image/png", "image/jpeg", "application/pdf", "application/octet-stream"}
    if file.content_type not in allowed:
        raise HTTPException(415, "Formato não suportado")
    provisional_key = f"{identity['tenant']}/patients/{identity['sub']}/{file.filename}"
    storage_key = LocalObjectStorage().put_private(provisional_key, content, file.content_type or "application/octet-stream")
    result = ocr_provider().extract(content, file.filename or "documento")
    item = PatientDocument(
        tenant_id=identity["tenant"],
        patient_id=identity["sub"],
        kind=kind,
        filename=file.filename or "documento",
        storage_key=storage_key,
        raw_ocr=result.raw_text,
        fields=result.fields,
        confidence=result.confidence,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return document_view(item)


@router.get("/patient/documents")
def list_patient_documents(identity: dict = Depends(current_identity), db: Session = Depends(get_db)):
    items = db.scalars(select(PatientDocument).where(PatientDocument.tenant_id == identity["tenant"], PatientDocument.patient_id == identity["sub"])).all()
    return {"items": [document_view(item) for item in items]}


@router.get("/patient/documents/{document_id}")
def get_patient_document(document_id: str, identity: dict = Depends(current_identity), db: Session = Depends(get_db)):
    item = db.scalar(select(PatientDocument).where(PatientDocument.id == document_id, PatientDocument.tenant_id == identity["tenant"], PatientDocument.patient_id == identity["sub"]))
    if not item:
        raise HTTPException(404, "Documento não encontrado")
    return document_view(item)


@router.post("/patient/documents/{document_id}/confirm")
def confirm_patient_document(
    document_id: str,
    payload: DocumentConfirm,
    identity: dict = Depends(current_identity),
    db: Session = Depends(get_db),
):
    item = db.scalar(select(PatientDocument).where(PatientDocument.id == document_id, PatientDocument.tenant_id == identity["tenant"], PatientDocument.patient_id == identity["sub"]))
    if not item:
        raise HTTPException(404, "Documento não encontrado")
    if not payload.confirmed:
        raise HTTPException(422, "Confirmação explícita é obrigatória")
    item.fields = payload.fields
    item.confirmed = True
    item.status = DocumentStatus.approved
    db.add(AuditEvent(tenant_id=identity["tenant"], actor_id=identity["sub"], action="patient_document.confirmed", resource_type="patient_document", resource_id=item.id, metadata_json={"fields": sorted(payload.fields)}))
    db.commit()
    return document_view(item)

