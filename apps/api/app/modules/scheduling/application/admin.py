from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.modules.identity.domain import Actor, UserRole
from app.modules.scheduling.application.service import SchedulingService
from app.shared.application import NotFoundError, ValidationError
from app.shared.infrastructure.models import (
    Appointment,
    AppointmentStatus,
    AuditEvent,
    AvailabilityBlock,
    AvailabilityRule,
    KnowledgeDocument,
    OutboxEvent,
    Role,
    User,
)
from app.shared.infrastructure.uow import uow_factory


class SchedulingAdminService:
    def __init__(self, factory=uow_factory):
        self._factory = factory

    def create_appointment(
        self, staff: Actor, patient_id: str, doctor_id: str, starts_at, reason: str
    ) -> dict:
        patient = Actor(patient_id, UserRole.PATIENT)
        result = SchedulingService(self._factory).create(patient, doctor_id, starts_at, reason)
        return result

    def cancel_appointment(self, staff: Actor, appointment_id: str) -> dict:
        return SchedulingService(self._factory).cancel(staff, appointment_id, staff_override=True)

    def reschedule_appointment(
        self,
        staff: Actor,
        appointment_id: str,
        starts_at,
        reason: str | None,
    ) -> dict:
        return SchedulingService(self._factory).reschedule(
            staff,
            appointment_id,
            starts_at,
            reason,
        )

    def list_rules(self) -> dict:
        with self._factory() as uow:
            rows = uow.session.scalars(
                select(AvailabilityRule).order_by(
                    AvailabilityRule.weekday, AvailabilityRule.starts_at
                )
            ).all()
            items = [self._rule_view(item) for item in rows]
            return self._page(items)

    def create_rule(self, actor: Actor, payload: dict) -> dict:
        if payload["starts_at"] >= payload["ends_at"]:
            raise ValidationError("Intervalo inválido")
        with self._factory() as uow:
            item = AvailabilityRule(**payload)
            uow.session.add(item)
            uow.flush()
            self._record_availability_change(
                uow.session, actor.id, "availability_rule", item.id, "created"
            )
            return self._rule_view(item)

    def update_rule(self, actor: Actor, rule_id: str, payload: dict) -> dict:
        with self._factory() as uow:
            item = uow.session.get(AvailabilityRule, rule_id)
            if not item:
                raise NotFoundError("Regra não encontrada")
            for key, value in payload.items():
                setattr(item, key, value)
            self._record_availability_change(
                uow.session, actor.id, "availability_rule", item.id, "updated"
            )
            return self._rule_view(item)

    def delete_rule(self, actor: Actor, rule_id: str) -> None:
        with self._factory() as uow:
            item = uow.session.get(AvailabilityRule, rule_id)
            if not item:
                raise NotFoundError("Regra não encontrada")
            self._record_availability_change(
                uow.session, actor.id, "availability_rule", item.id, "deleted"
            )
            uow.session.delete(item)

    def list_blocks(self) -> dict:
        with self._factory() as uow:
            rows = uow.session.scalars(
                select(AvailabilityBlock).order_by(AvailabilityBlock.starts_at)
            ).all()
            items = [self._block_view(item) for item in rows]
            return self._page(items)

    def create_block(self, actor: Actor, payload: dict) -> dict:
        if payload["starts_at"] >= payload["ends_at"]:
            raise ValidationError("Intervalo inválido")
        with self._factory() as uow:
            item = AvailabilityBlock(**payload)
            uow.session.add(item)
            uow.flush()
            self._record_availability_change(
                uow.session, actor.id, "availability_block", item.id, "created"
            )
            return self._block_view(item)

    def delete_block(self, actor: Actor, block_id: str) -> None:
        with self._factory() as uow:
            item = uow.session.get(AvailabilityBlock, block_id)
            if not item:
                raise NotFoundError("Bloqueio não encontrado")
            self._record_availability_change(
                uow.session, actor.id, "availability_block", item.id, "deleted"
            )
            uow.session.delete(item)

    @staticmethod
    def _record_availability_change(
        session, actor_id: str, resource_type: str, resource_id: str, action: str
    ) -> None:
        event_type = f"{resource_type}.{action}"
        session.add(
            AuditEvent(
                actor_id=actor_id,
                action=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )
        session.add(
            OutboxEvent(
                aggregate_type=resource_type,
                aggregate_id=resource_id,
                event_type=event_type,
                payload={"id": resource_id},
            )
        )

    def dashboard(self) -> dict:
        with self._factory() as uow:
            today = datetime.now(timezone.utc).date()
            start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
            end = start.replace(hour=23, minute=59, second=59)
            appointments = (
                select(func.count())
                .select_from(Appointment)
                .where(Appointment.starts_at.between(start, end))
            )
            return {
                "appointments_today": uow.session.scalar(appointments) or 0,
                "confirmed_today": uow.session.scalar(
                    appointments.where(Appointment.status == AppointmentStatus.confirmed)
                )
                or 0,
                "patients": uow.session.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(User.role == Role.patient, User.archived_at.is_(None))
                )
                or 0,
                "knowledge_pending": uow.session.scalar(
                    select(func.count())
                    .select_from(KnowledgeDocument)
                    .where(KnowledgeDocument.status == "review_required")
                )
                or 0,
            }

    def patients(self, query: str = "") -> dict:
        from app.modules.identity.infrastructure.security import mask_cpf

        with self._factory() as uow:
            statement = select(User).where(User.role == Role.patient, User.archived_at.is_(None))
            if query:
                statement = statement.where(User.name.ilike(f"%{query}%"))
            rows = uow.session.scalars(statement.order_by(User.name)).all()
            items = [
                {
                    "id": item.id,
                    "name": item.name,
                    "cpf": mask_cpf(item.cpf_encrypted),
                    "birth_date": item.birth_date,
                    "email": item.email,
                    "created_at": item.created_at,
                }
                for item in rows
            ]
            return self._page(items)

    @staticmethod
    def _rule_view(item) -> dict:
        return {
            column: getattr(item, column)
            for column in (
                "id",
                "doctor_id",
                "unit_id",
                "weekday",
                "starts_at",
                "ends_at",
                "slot_minutes",
                "valid_from",
                "valid_until",
                "active",
            )
        }

    @staticmethod
    def _block_view(item) -> dict:
        return {
            column: getattr(item, column)
            for column in ("id", "doctor_id", "starts_at", "ends_at", "reason")
        }

    @staticmethod
    def _page(items: list[dict]) -> dict:
        return {"items": items, "total": len(items), "page": 1, "page_size": len(items)}
