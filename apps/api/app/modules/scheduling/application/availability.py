from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.shared.infrastructure.models import (
    Appointment,
    AppointmentStatus,
    AvailabilityBlock,
    AvailabilityRule,
    Doctor,
    Unit,
)


class SlotCalculator:
    @classmethod
    def calculate(
        cls,
        session,
        timezone_name: str,
        start: date,
        end: date,
        doctor_id: str | None = None,
        specialty_id: str | None = None,
        unit_id: str | None = None,
        insurer_id: str | None = None,
        period: str | None = None,
        exclude_appointment_id: str | None = None,
    ) -> list[dict]:
        doctors = cls._doctors(session, doctor_id, specialty_id, insurer_id)
        start_utc, end_utc = cls._utc_window(start, end, timezone_name)
        busy_query = select(Appointment).where(
            Appointment.doctor_id.in_(doctors),
            Appointment.status == AppointmentStatus.confirmed,
            Appointment.starts_at < end_utc,
            Appointment.ends_at > start_utc,
        )
        if exclude_appointment_id:
            busy_query = busy_query.where(Appointment.id != exclude_appointment_id)
        busy = session.scalars(busy_query).all()
        blocks = session.scalars(
            select(AvailabilityBlock).where(
                AvailabilityBlock.doctor_id.in_(doctors),
                AvailabilityBlock.starts_at < end_utc,
                AvailabilityBlock.ends_at > start_utc,
            )
        ).all()
        rules = session.scalars(
            select(AvailabilityRule).where(
                AvailabilityRule.doctor_id.in_(doctors),
                AvailabilityRule.active.is_(True),
            )
        ).all()
        units = {
            item.id: item
            for item in session.scalars(select(Unit).where(Unit.active.is_(True))).all()
        }
        candidates = cls._rule_candidates(rules, start, end, timezone_name, unit_id)
        return cls._serialize(candidates, doctors, units, busy, blocks, period, timezone_name)

    @staticmethod
    def _doctors(session, doctor_id, specialty_id, insurer_id) -> dict:
        query = select(Doctor).where(Doctor.active.is_(True), Doctor.archived_at.is_(None))
        if doctor_id:
            query = query.where(Doctor.id == doctor_id)
        if specialty_id:
            query = query.where(Doctor.specialty_id == specialty_id)
        return {
            item.id: item
            for item in session.scalars(query).all()
            if not insurer_id or any(value.id == insurer_id for value in item.insurers)
        }

    @staticmethod
    def _utc_window(start: date, end: date, timezone_name: str) -> tuple[datetime, datetime]:
        zone = ZoneInfo(timezone_name)
        lower = datetime.combine(start, time.min, tzinfo=zone).astimezone(timezone.utc)
        upper = datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone).astimezone(
            timezone.utc
        )
        return lower, upper

    @classmethod
    def _rule_candidates(cls, rules, start, end, timezone_name, unit_id) -> dict:
        candidates = {}
        current = start
        while current <= end:
            for rule in rules:
                if current.weekday() != rule.weekday or (unit_id and rule.unit_id != unit_id):
                    continue
                if (rule.valid_from and current < rule.valid_from) or (
                    rule.valid_until and current > rule.valid_until
                ):
                    continue
                cursor = cls._local_to_utc(current, rule.starts_at, timezone_name)
                limit = cls._local_to_utc(current, rule.ends_at, timezone_name)
                while cursor + timedelta(minutes=rule.slot_minutes) <= limit:
                    candidates[(rule.doctor_id, cursor)] = (
                        rule.unit_id,
                        cursor + timedelta(minutes=rule.slot_minutes),
                    )
                    cursor += timedelta(minutes=rule.slot_minutes)
            current += timedelta(days=1)
        return candidates

    @classmethod
    def _serialize(cls, candidates, doctors, units, busy, blocks, period, timezone_name):
        items, now = [], datetime.now(timezone.utc)
        for (doctor_id, starts_at), (unit_id, ends_at) in sorted(
            candidates.items(), key=lambda row: row[0][1]
        ):
            hour = starts_at.astimezone(ZoneInfo(timezone_name)).hour
            if starts_at <= now or unit_id not in units or not cls._period_matches(hour, period):
                continue
            if any(
                row.doctor_id == doctor_id
                and cls._overlaps(starts_at, ends_at, row.starts_at, row.ends_at)
                for row in [*busy, *blocks]
            ):
                continue
            doctor, unit = doctors[doctor_id], units[unit_id]
            items.append(
                {
                    "id": f"{doctor_id}:{starts_at.isoformat()}",
                    "doctor": {"id": doctor.id, "name": doctor.name, "crm": doctor.crm},
                    "unit": {"id": unit.id, "name": unit.name, "address": unit.address},
                    "starts_at": starts_at.isoformat(),
                    "ends_at": ends_at.isoformat(),
                    "timezone": timezone_name,
                }
            )
        return items

    @staticmethod
    def _period_matches(hour: int, period: str | None) -> bool:
        return (
            period is None
            or (period == "morning" and hour < 12)
            or (period == "afternoon" and 12 <= hour < 18)
            or (period == "evening" and hour >= 18)
        )

    @classmethod
    def _overlaps(cls, start, end, other_start, other_end) -> bool:
        return cls.to_utc(other_start) < cls.to_utc(end) and cls.to_utc(other_end) > cls.to_utc(
            start
        )

    @staticmethod
    def _local_to_utc(day: date, value: time, timezone_name: str) -> datetime:
        return datetime.combine(day, value, tzinfo=ZoneInfo(timezone_name)).astimezone(timezone.utc)

    @staticmethod
    def to_utc(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
