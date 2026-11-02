from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.conversation import local_datetime, local_to_utc, tenant_timezone
from app.db import get_db
from app.models import (
    Appointment,
    AppointmentHistory,
    AppointmentStatus,
    AuditEvent,
    Availability,
    AvailabilityBlock,
    AvailabilityRule,
    Doctor,
    Insurer,
    Specialty,
    Tenant,
    Unit,
)
from app.security import current_identity

router = APIRouter(tags=["operations"])


class AppointmentCreate(BaseModel):
    doctor_id: str
    starts_at: datetime
    reason: str = "Consulta"
    confirmed: bool


def lock_appointment_slot(db: Session, tenant_id: str, doctor_id: str, starts_at: datetime) -> None:
    """Serialize bookings for one doctor and start time inside the transaction."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        lock_key = f"appointment:{tenant_id}:{doctor_id}:{starts_at.isoformat()}"
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )


def appointment_view(item: Appointment, doctors: dict | None = None, units: dict | None = None) -> dict:
    return {
        "id": item.id,
        "doctor_id": item.doctor_id,
        "doctor": (doctors or {}).get(item.doctor_id),
        "unit_id": item.unit_id,
        "unit": (units or {}).get(item.unit_id),
        "starts_at": item.starts_at,
        "ends_at": item.ends_at,
        "status": item.status.value,
        "reason": item.reason,
    }


def _overlaps(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
    return _utc(other_start) < _utc(end) and _utc(other_end) > _utc(start)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def available_slots(
    db: Session,
    tenant_id: str,
    from_date: date,
    to_date: date,
    doctor_id: str | None = None,
    specialty_id: str | None = None,
    unit_id: str | None = None,
    insurer_id: str | None = None,
    period: str | None = None,
) -> list[dict]:
    tenant = db.get(Tenant, tenant_id)
    timezone_name = tenant.timezone if tenant else "America/Sao_Paulo"
    zone = tenant_timezone(timezone_name)
    doctors_query = select(Doctor).where(
        Doctor.tenant_id == tenant_id,
        Doctor.active.is_(True),
        Doctor.deleted_at.is_(None),
    )
    if doctor_id:
        doctors_query = doctors_query.where(Doctor.id == doctor_id)
    if specialty_id:
        doctors_query = doctors_query.where(Doctor.specialty_id == specialty_id)
    doctors = {
        item.id: item
        for item in db.scalars(doctors_query)
        if not insurer_id or insurer_id in item.insurer_ids
    }
    units = {item.id: item for item in db.scalars(select(Unit).where(Unit.tenant_id == tenant_id, Unit.active.is_(True)))}
    starts = datetime.combine(from_date, time.min, tzinfo=zone).astimezone(timezone.utc)
    ends = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    busy = db.scalars(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.status == AppointmentStatus.confirmed,
            Appointment.starts_at < ends,
            Appointment.ends_at > starts,
        )
    ).all()
    blocks = db.scalars(
        select(AvailabilityBlock).where(
            AvailabilityBlock.tenant_id == tenant_id,
            AvailabilityBlock.starts_at < ends,
            AvailabilityBlock.ends_at > starts,
        )
    ).all()
    candidates: dict[tuple[str, datetime], tuple[str, datetime]] = {}
    explicit = db.scalars(
        select(Availability).where(
            Availability.tenant_id == tenant_id,
            Availability.starts_at < ends,
            Availability.ends_at > starts,
        )
    ).all()
    for slot in explicit:
        if slot.doctor_id in doctors and (not unit_id or slot.unit_id == unit_id):
            candidates[(slot.doctor_id, _utc(slot.starts_at))] = (slot.unit_id, _utc(slot.ends_at))
    rules_query = select(AvailabilityRule).where(
        AvailabilityRule.tenant_id == tenant_id,
        AvailabilityRule.active.is_(True),
    )
    rules = db.scalars(rules_query).all()
    current = from_date
    while current <= to_date:
        for rule in rules:
            if rule.doctor_id not in doctors or current.weekday() != rule.weekday:
                continue
            if unit_id and rule.unit_id != unit_id:
                continue
            if rule.valid_from and current < rule.valid_from:
                continue
            if rule.valid_until and current > rule.valid_until:
                continue
            cursor = local_to_utc(current, rule.starts_at, timezone_name)
            limit = local_to_utc(current, rule.ends_at, timezone_name)
            while cursor + timedelta(minutes=rule.slot_minutes) <= limit:
                candidates[(rule.doctor_id, cursor)] = (
                    rule.unit_id,
                    cursor + timedelta(minutes=rule.slot_minutes),
                )
                cursor += timedelta(minutes=rule.slot_minutes)
        current += timedelta(days=1)
    items = []
    now = datetime.now(timezone.utc)
    for (candidate_doctor, start), (candidate_unit, end) in sorted(candidates.items(), key=lambda item: item[0][1]):
        if candidate_unit not in units:
            continue
        if start <= now:
            continue
        local_start = local_datetime(start, timezone_name)
        if period == "morning" and local_start.hour >= 12:
            continue
        if period == "afternoon" and not 12 <= local_start.hour < 18:
            continue
        if period == "evening" and local_start.hour < 18:
            continue
        if any(
            appointment.doctor_id == candidate_doctor
            and _overlaps(start, end, appointment.starts_at, appointment.ends_at)
            for appointment in busy
        ):
            continue
        if any(
            block.doctor_id == candidate_doctor
            and _overlaps(start, end, block.starts_at, block.ends_at)
            for block in blocks
        ):
            continue
        doctor = doctors[candidate_doctor]
        unit = units[candidate_unit]
        items.append(
            {
                "id": f"{candidate_doctor}:{start.isoformat()}",
                "doctor": {"id": doctor.id, "name": doctor.name, "crm": doctor.crm},
                "unit": {"id": unit.id, "name": unit.name, "address": unit.address},
                "starts_at": start,
                "ends_at": end,
                "timezone": timezone_name,
            }
        )
    return items


def create_patient_appointment(payload: AppointmentCreate, identity: dict, db: Session) -> dict:
    if identity["role"] != "patient":
        raise HTTPException(403, "Apenas pacientes podem agendar por este endpoint")
    if not payload.confirmed:
        raise HTTPException(422, "Confirmação explícita é obrigatória")
    requested = payload.starts_at
    if requested.tzinfo is None:
        requested = requested.replace(tzinfo=timezone.utc)
    lock_appointment_slot(db, identity["tenant"], payload.doctor_id, requested)
    slots = available_slots(
        db,
        identity["tenant"],
        requested.date(),
        requested.date(),
        doctor_id=payload.doctor_id,
    )
    slot = next((item for item in slots if item["starts_at"] == requested), None)
    if not slot:
        raise HTTPException(409, "Horário indisponível")
    item = Appointment(
        tenant_id=identity["tenant"],
        patient_id=identity["sub"],
        doctor_id=payload.doctor_id,
        unit_id=slot["unit"]["id"],
        starts_at=slot["starts_at"],
        ends_at=slot["ends_at"],
        reason=payload.reason,
    )
    db.add(item)
    try:
        db.flush()
        db.add(AuditEvent(tenant_id=identity["tenant"], actor_id=identity["sub"], action="appointment.created", resource_type="appointment", resource_id=item.id))
        db.add(AppointmentHistory(tenant_id=identity["tenant"], appointment_id=item.id, actor_id=identity["sub"], from_status=None, to_status=AppointmentStatus.confirmed.value))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Horário já reservado") from exc
    db.refresh(item)
    return appointment_view(item)


def cancel_patient_appointment(appointment_id: str, identity: dict, db: Session) -> dict:
    item = db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.tenant_id == identity["tenant"],
            Appointment.patient_id == identity["sub"],
        )
    )
    if not item:
        raise HTTPException(404, "Agendamento não encontrado")
    if item.status == AppointmentStatus.cancelled:
        return appointment_view(item)
    policy = db.get(Tenant, identity["tenant"])
    notice = policy.cancellation_notice_hours if policy else 0
    starts_at = item.starts_at if item.starts_at.tzinfo else item.starts_at.replace(tzinfo=timezone.utc)
    if notice and datetime.now(timezone.utc) > starts_at - timedelta(hours=notice):
        raise HTTPException(409, f"Cancelamentos exigem antecedência de {notice} horas")
    item.status = AppointmentStatus.cancelled
    item.cancelled_at = datetime.now(timezone.utc)
    db.add(AuditEvent(tenant_id=identity["tenant"], actor_id=identity["sub"], action="appointment.cancelled", resource_type="appointment", resource_id=item.id))
    db.add(AppointmentHistory(tenant_id=identity["tenant"], appointment_id=item.id, actor_id=identity["sub"], from_status=AppointmentStatus.confirmed.value, to_status=AppointmentStatus.cancelled.value))
    db.commit()
    return appointment_view(item)


@router.get("/directory/doctors")
def public_doctor_directory(tenant_id: str = "clinic-alyvo", db: Session = Depends(get_db)):
    rows = db.execute(
        select(Doctor, Specialty, Unit)
        .join(Specialty, Doctor.specialty_id == Specialty.id)
        .join(Unit, Doctor.unit_id == Unit.id)
        .where(Doctor.tenant_id == tenant_id, Doctor.active.is_(True), Doctor.deleted_at.is_(None))
        .order_by(Doctor.name)
    ).all()
    insurers = {item.id: item.name for item in db.scalars(select(Insurer).where(Insurer.tenant_id == tenant_id, Insurer.active.is_(True)))}
    return {"items": [{"id": doctor.id, "name": doctor.name, "crm": doctor.crm, "specialty": specialty.name, "unit": unit.name, "insurers": [insurers[item] for item in doctor.insurer_ids if item in insurers]} for doctor, specialty, unit in rows]}


@router.get("/availability")
def list_availability(
    day: date | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    doctor_id: str | None = None,
    specialty_id: str | None = None,
    unit_id: str | None = None,
    insurer_id: str | None = None,
    period: str | None = None,
    tenant_id: str = "clinic-alyvo",
    db: Session = Depends(get_db),
):
    start = day or from_date or datetime.now(timezone.utc).date()
    end = day or to_date or start + timedelta(days=14)
    if (end - start).days > 31:
        raise HTTPException(422, "Intervalo máximo de 31 dias")
    tenant = db.get(Tenant, tenant_id)
    timezone_name = tenant.timezone if tenant else "America/Sao_Paulo"
    items = available_slots(
        db, tenant_id, start, end, doctor_id, specialty_id, unit_id, insurer_id, period
    )
    serialized = [
        {
            **item,
            "starts_at": local_datetime(item["starts_at"], timezone_name),
            "ends_at": local_datetime(item["ends_at"], timezone_name),
        }
        for item in items
    ]
    return {"items": serialized, "source": "postgresql", "timezone": timezone_name}


@router.post("/appointments", status_code=201)
def create_appointment(payload: AppointmentCreate, identity: dict = Depends(current_identity), db: Session = Depends(get_db)):
    return create_patient_appointment(payload, identity, db)


@router.get("/appointments/me")
def my_appointments(identity: dict = Depends(current_identity), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Appointment).where(
            Appointment.tenant_id == identity["tenant"],
            Appointment.patient_id == identity["sub"],
        ).order_by(Appointment.starts_at)
    ).all()
    doctors = {item.id: item.name for item in db.scalars(select(Doctor).where(Doctor.tenant_id == identity["tenant"]))}
    units = {item.id: item.name for item in db.scalars(select(Unit).where(Unit.tenant_id == identity["tenant"]))}
    return {"items": [appointment_view(item, doctors, units) for item in rows]}


@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(appointment_id: str, confirmed: bool = True, identity: dict = Depends(current_identity), db: Session = Depends(get_db)):
    if not confirmed:
        raise HTTPException(422, "Confirmação explícita é obrigatória")
    return cancel_patient_appointment(appointment_id, identity, db)
