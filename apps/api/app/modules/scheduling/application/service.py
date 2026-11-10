from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.modules.identity.domain import Actor, UserRole
from app.modules.scheduling.application.availability import SlotCalculator
from app.modules.scheduling.domain import CancellationPolicy
from app.shared.application import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.shared.infrastructure.models import (
    Appointment,
    AppointmentHistory,
    AppointmentStatus,
    AuditEvent,
    ClinicProfile,
    Doctor,
    OutboxEvent,
    Unit,
    User,
)
from app.shared.infrastructure.uow import uow_factory


class SchedulingService:
    def __init__(self, factory=uow_factory):
        self._factory = factory

    def availability(
        self,
        start: date,
        end: date,
        doctor_id: str | None = None,
        specialty_id: str | None = None,
        unit_id: str | None = None,
        insurer_id: str | None = None,
        period: str | None = None,
    ) -> dict:
        if end < start or (end - start).days > 31:
            raise ValidationError("Intervalo máximo de 31 dias")
        with self._factory() as uow:
            profile = uow.session.get(ClinicProfile, 1)
            timezone_name = profile.timezone if profile else "America/Sao_Paulo"
            items = SlotCalculator.calculate(
                uow.session,
                timezone_name,
                start,
                end,
                doctor_id,
                specialty_id,
                unit_id,
                insurer_id,
                period,
            )
            return {
                "items": items,
                "total": len(items),
                "page": 1,
                "page_size": len(items),
                "timezone": timezone_name,
            }

    def create(self, actor: Actor, doctor_id: str, starts_at: datetime, reason: str) -> dict:
        if actor.role != UserRole.PATIENT:
            raise ForbiddenError("Apenas pacientes podem agendar")
        with self._factory() as uow:
            requested = SlotCalculator.to_utc(starts_at)
            self._lock(uow.session, doctor_id, requested)
            profile = uow.session.get(ClinicProfile, 1)
            zone = profile.timezone if profile else "America/Sao_Paulo"
            slots = SlotCalculator.calculate(
                uow.session, zone, requested.date(), requested.date(), doctor_id
            )
            slot = next(
                (item for item in slots if datetime.fromisoformat(item["starts_at"]) == requested),
                None,
            )
            if not slot:
                raise ConflictError("Horário indisponível", code="appointment_conflict")
            item = Appointment(
                patient_id=actor.id,
                doctor_id=doctor_id,
                unit_id=slot["unit"]["id"],
                starts_at=requested,
                ends_at=datetime.fromisoformat(slot["ends_at"]),
                reason=reason,
            )
            uow.session.add(item)
            try:
                uow.flush()
            except IntegrityError as exc:
                raise ConflictError("Horário já reservado", code="appointment_conflict") from exc
            self._history(uow.session, item, actor.id, None, AppointmentStatus.confirmed)
            self._audit(uow.session, actor.id, "appointment.created", item.id)
            return self._appointment_view(uow.session, item)

    def cancel(self, actor: Actor, appointment_id: str, staff_override: bool = False) -> dict:
        with self._factory() as uow:
            statement = select(Appointment).where(Appointment.id == appointment_id)
            if actor.role == UserRole.PATIENT:
                statement = statement.where(Appointment.patient_id == actor.id)
            item = uow.session.scalar(statement)
            if not item:
                raise NotFoundError("Agendamento não encontrado")
            if item.status == AppointmentStatus.cancelled:
                return self._appointment_view(uow.session, item)
            profile = uow.session.get(ClinicProfile, 1)
            policy = CancellationPolicy(profile.cancellation_notice_hours if profile else 0)
            now = datetime.now(timezone.utc)
            if not policy.allows(SlotCalculator.to_utc(item.starts_at), now, staff_override):
                raise ConflictError(
                    f"Cancelamentos exigem antecedência de {policy.notice_hours} horas"
                )
            item.status, item.cancelled_at = AppointmentStatus.cancelled, now
            self._history(
                uow.session,
                item,
                actor.id,
                AppointmentStatus.confirmed,
                AppointmentStatus.cancelled,
            )
            self._audit(uow.session, actor.id, "appointment.cancelled", item.id)
            return self._appointment_view(uow.session, item)

    def reschedule(
        self,
        actor: Actor,
        appointment_id: str,
        starts_at: datetime,
        reason: str | None = None,
    ) -> dict:
        with self._factory() as uow:
            item = uow.session.get(Appointment, appointment_id)
            if not item:
                raise NotFoundError("Agendamento não encontrado")
            requested = SlotCalculator.to_utc(starts_at)
            self._lock(uow.session, item.doctor_id, requested)
            profile = uow.session.get(ClinicProfile, 1)
            zone = profile.timezone if profile else "America/Sao_Paulo"
            slots = SlotCalculator.calculate(
                uow.session,
                zone,
                requested.date(),
                requested.date(),
                item.doctor_id,
                exclude_appointment_id=item.id,
            )
            slot = next(
                (
                    value
                    for value in slots
                    if datetime.fromisoformat(value["starts_at"]) == requested
                ),
                None,
            )
            if not slot:
                raise ConflictError("Horário indisponível", code="appointment_conflict")
            item.starts_at = requested
            item.ends_at = datetime.fromisoformat(slot["ends_at"])
            item.unit_id = slot["unit"]["id"]
            if reason is not None:
                item.reason = reason
            self._history(
                uow.session,
                item,
                actor.id,
                AppointmentStatus.confirmed,
                AppointmentStatus.confirmed,
                "rescheduled",
            )
            self._audit(uow.session, actor.id, "appointment.rescheduled", item.id)
            return self._appointment_view(uow.session, item)

    def list_mine(self, actor: Actor) -> dict:
        if actor.role != UserRole.PATIENT:
            raise ForbiddenError("Acesso restrito ao paciente")
        with self._factory() as uow:
            rows = uow.session.scalars(
                select(Appointment)
                .where(Appointment.patient_id == actor.id)
                .order_by(Appointment.starts_at)
            ).all()
            return {
                "items": [self._appointment_view(uow.session, item) for item in rows],
                "total": len(rows),
                "page": 1,
                "page_size": len(rows),
            }

    def agenda(
        self, start: date, end: date, doctor_id: str | None = None, unit_id: str | None = None
    ) -> dict:
        with self._factory() as uow:
            statement = select(Appointment).where(
                Appointment.starts_at
                < datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc),
                Appointment.ends_at > datetime.combine(start, time.min, tzinfo=timezone.utc),
            )
            if doctor_id:
                statement = statement.where(Appointment.doctor_id == doctor_id)
            if unit_id:
                statement = statement.where(Appointment.unit_id == unit_id)
            rows = uow.session.scalars(statement.order_by(Appointment.starts_at)).all()
            items = [
                self._appointment_view(uow.session, item, include_patient=True) for item in rows
            ]
            return {"items": items, "total": len(items), "page": 1, "page_size": len(items)}

    @staticmethod
    def _lock(session, doctor_id: str, starts_at: datetime) -> None:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"appointment:{doctor_id}:{starts_at.isoformat()}"},
            )

    @staticmethod
    def _history(session, item, actor_id, previous, current, reason: str = "") -> None:
        session.add(
            AppointmentHistory(
                appointment_id=item.id,
                actor_id=actor_id,
                from_status=previous.value if previous else None,
                to_status=current.value,
                reason=reason,
            )
        )

    @staticmethod
    def _audit(session, actor_id: str, action: str, resource_id: str) -> None:
        session.add(
            AuditEvent(
                actor_id=actor_id,
                action=action,
                resource_type="appointment",
                resource_id=resource_id,
            )
        )
        session.add(
            OutboxEvent(
                aggregate_type="appointment",
                aggregate_id=resource_id,
                event_type=action,
                payload={"id": resource_id},
            )
        )

    @staticmethod
    def _appointment_view(session, item: Appointment, include_patient: bool = False) -> dict:
        doctor, unit = session.get(Doctor, item.doctor_id), session.get(Unit, item.unit_id)
        view = {
            "id": item.id,
            "patient_id": item.patient_id,
            "doctor_id": item.doctor_id,
            "doctor": doctor.name if doctor else None,
            "unit_id": item.unit_id,
            "unit": unit.name if unit else None,
            "starts_at": item.starts_at.isoformat(),
            "ends_at": item.ends_at.isoformat(),
            "status": item.status.value,
            "reason": item.reason,
        }
        if include_patient:
            patient = session.get(User, item.patient_id)
            view["patient"] = patient.name if patient else None
        return view
