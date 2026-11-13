from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.catalog.application.doctor_search import filter_doctors, recognized_entity_ids
from app.modules.catalog.domain import CatalogKind
from app.shared.application import ConflictError, NotFoundError, ValidationError
from app.shared.infrastructure.models import (
    AuditEvent,
    Doctor,
    Exam,
    Insurer,
    OutboxEvent,
    Specialty,
    Unit,
)
from app.shared.infrastructure.uow import uow_factory

MODELS = {
    CatalogKind.SPECIALTY: Specialty,
    CatalogKind.UNIT: Unit,
    CatalogKind.INSURER: Insurer,
    CatalogKind.EXAM: Exam,
}


class CatalogService:
    def __init__(self, factory=uow_factory):
        self._factory = factory

    def list_catalog(
        self,
        kind: CatalogKind,
        query: str = "",
        include_inactive: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        with self._factory() as uow:
            model = MODELS[kind]
            statement = select(model)
            if query:
                statement = statement.where(model.name.ilike(f"%{query}%"))
            if not include_inactive:
                statement = statement.where(model.active.is_(True))
            total = uow.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
            size = min(max(page_size, 1), 100)
            rows = uow.session.scalars(
                statement.order_by(model.name).offset((max(page, 1) - 1) * size).limit(size)
            ).all()
            return {
                "items": [self._catalog_view(item) for item in rows],
                "total": total,
                "page": page,
                "page_size": size,
            }

    def create_catalog(self, kind: CatalogKind, payload: dict, actor_id: str) -> dict:
        with self._factory() as uow:
            item = self._new_catalog(uow.session, kind, payload)
            uow.session.add(item)
            self._flush_unique(uow)
            self._record_change(
                uow.session, actor_id, kind.value, item.id, "created", self._catalog_view(item)
            )
            return self._catalog_view(item)

    def update_catalog(self, kind: CatalogKind, item_id: str, payload: dict, actor_id: str) -> dict:
        with self._factory() as uow:
            item = uow.session.get(MODELS[kind], item_id)
            if not item:
                raise NotFoundError("Registro não encontrado")
            self._apply_catalog(uow.session, kind, item, payload)
            self._flush_unique(uow)
            self._record_change(
                uow.session, actor_id, kind.value, item.id, "updated", self._catalog_view(item)
            )
            return self._catalog_view(item)

    def archive_catalog(self, kind: CatalogKind, item_id: str, actor_id: str) -> None:
        with self._factory() as uow:
            item = uow.session.get(MODELS[kind], item_id)
            if not item:
                raise NotFoundError("Registro não encontrado")
            item.active = False
            self._record_change(
                uow.session, actor_id, kind.value, item.id, "archived", {"id": item.id}
            )

    def list_doctors(
        self,
        query: str = "",
        include_inactive: bool = False,
        doctor_ids: list[str] | None = None,
    ) -> dict:
        with self._factory() as uow:
            statement = select(Doctor)
            if not include_inactive:
                statement = statement.where(Doctor.active.is_(True), Doctor.archived_at.is_(None))
            rows = uow.session.scalars(statement.order_by(Doctor.name)).all()
            if doctor_ids:
                selected = set(doctor_ids)
                rows = [doctor for doctor in rows if doctor.id in selected]
            if query:
                rows = filter_doctors(rows, query)
            return {
                "items": [self._doctor_view(item) for item in rows],
                "total": len(rows),
                "page": 1,
                "page_size": len(rows),
            }

    def resolve_doctor_entities(self, query: str) -> dict[str, list[str]]:
        """Resolve catalog-backed identifiers without trusting model-generated IDs."""

        with self._factory() as uow:
            doctors = list(
                uow.session.scalars(
                    select(Doctor).where(Doctor.active.is_(True), Doctor.archived_at.is_(None))
                ).all()
            )
            return recognized_entity_ids(doctors, query)

    def create_doctor(self, payload: dict, actor_id: str) -> dict:
        with self._factory() as uow:
            specialty, unit, insurers = self._doctor_relations(uow.session, payload)
            doctor = Doctor(
                name=payload["name"],
                crm=payload["crm"],
                specialty=specialty,
                unit=unit,
                insurers=insurers,
                active=payload.get("active", True),
            )
            uow.session.add(doctor)
            self._flush_unique(uow)
            view = self._doctor_view(doctor)
            self._record_change(uow.session, actor_id, "doctor", doctor.id, "created", view)
            return view

    def update_doctor(self, doctor_id: str, payload: dict, actor_id: str) -> dict:
        with self._factory() as uow:
            doctor = uow.session.get(Doctor, doctor_id)
            if not doctor:
                raise NotFoundError("Médico não encontrado")
            specialty, unit, insurers = self._doctor_relations(uow.session, payload)
            doctor.name, doctor.crm = payload["name"], payload["crm"]
            doctor.specialty, doctor.unit, doctor.insurers = specialty, unit, insurers
            doctor.active = payload.get("active", True)
            self._flush_unique(uow)
            view = self._doctor_view(doctor)
            self._record_change(uow.session, actor_id, "doctor", doctor.id, "updated", view)
            return view

    def archive_doctor(self, doctor_id: str, actor_id: str) -> None:
        with self._factory() as uow:
            doctor = uow.session.get(Doctor, doctor_id)
            if not doctor:
                raise NotFoundError("Médico não encontrado")
            doctor.active = False
            doctor.archived_at = datetime.now(timezone.utc)
            self._record_change(
                uow.session, actor_id, "doctor", doctor.id, "archived", {"id": doctor.id}
            )

    @staticmethod
    def _doctor_relations(session: Session, payload: dict) -> tuple[Specialty, Unit, list[Insurer]]:
        specialty = session.get(Specialty, payload["specialty_id"])
        unit = session.get(Unit, payload["unit_id"])
        insurers = list(
            session.scalars(
                select(Insurer).where(Insurer.id.in_(payload.get("insurer_ids", [])))
            ).all()
        )
        if not specialty or not specialty.active:
            raise ValidationError("Especialidade inválida")
        if not unit or not unit.active:
            raise ValidationError("Unidade inválida")
        if len(insurers) != len(set(payload.get("insurer_ids", []))):
            raise ValidationError("Convênio inválido")
        return specialty, unit, insurers

    @staticmethod
    def _new_catalog(session: Session, kind: CatalogKind, payload: dict):
        if kind == CatalogKind.SPECIALTY:
            return Specialty(
                name=payload["name"],
                description=payload.get("description", ""),
                active=payload.get("active", True),
            )
        if kind == CatalogKind.UNIT:
            return Unit(
                name=payload["name"],
                address=payload.get("address", ""),
                active=payload.get("active", True),
            )
        if kind == CatalogKind.INSURER:
            return Insurer(name=payload["name"], active=payload.get("active", True))
        units = list(
            session.scalars(select(Unit).where(Unit.id.in_(payload.get("unit_ids", [])))).all()
        )
        return Exam(
            name=payload["name"],
            preparation=payload.get("preparation", ""),
            units=units,
            active=payload.get("active", True),
        )

    @staticmethod
    def _apply_catalog(session: Session, kind: CatalogKind, item, payload: dict) -> None:
        item.name = payload["name"]
        item.active = payload.get("active", True)
        for field in ("description", "address", "preparation"):
            if hasattr(item, field):
                setattr(item, field, payload.get(field, ""))
        if kind == CatalogKind.EXAM:
            item.units = list(
                session.scalars(select(Unit).where(Unit.id.in_(payload.get("unit_ids", [])))).all()
            )

    @staticmethod
    def _catalog_view(item) -> dict:
        view = {"id": item.id, "name": item.name, "active": item.active}
        for field in ("description", "address", "preparation"):
            if hasattr(item, field):
                view[field] = getattr(item, field)
        if isinstance(item, Exam):
            view["unit_ids"] = [unit.id for unit in item.units]
        return view

    @staticmethod
    def _doctor_view(doctor: Doctor) -> dict:
        return {
            "id": doctor.id,
            "name": doctor.name,
            "crm": doctor.crm,
            "specialty_id": doctor.specialty_id,
            "specialty": doctor.specialty.name,
            "unit_id": doctor.unit_id,
            "unit": doctor.unit.name,
            "insurer_ids": [item.id for item in doctor.insurers],
            "insurers": [item.name for item in doctor.insurers],
            "active": doctor.active,
        }

    @staticmethod
    def _record_change(
        session: Session, actor_id: str, resource: str, resource_id: str, action: str, payload: dict
    ) -> None:
        session.add(
            AuditEvent(
                actor_id=actor_id,
                action=f"{resource}.{action}",
                resource_type=resource,
                resource_id=resource_id,
            )
        )
        session.add(
            OutboxEvent(
                aggregate_type=resource,
                aggregate_id=resource_id,
                event_type=f"{resource}.{action}",
                payload=payload,
            )
        )

    @staticmethod
    def _flush_unique(uow) -> None:
        try:
            uow.flush()
        except IntegrityError as exc:
            raise ConflictError("Já existe um registro com estes dados") from exc
