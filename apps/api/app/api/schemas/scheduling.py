from datetime import date, datetime, time

from pydantic import Field

from app.api.schemas.common import StrictModel


class AppointmentCreate(StrictModel):
    doctor_id: str
    starts_at: datetime
    reason: str = Field(default="Consulta", max_length=200)


class StaffAppointmentCreate(AppointmentCreate):
    patient_id: str


class AppointmentUpdate(StrictModel):
    starts_at: datetime
    reason: str | None = Field(default=None, max_length=200)


class AppointmentView(StrictModel):
    id: str
    patient_id: str
    patient: str | None = None
    doctor_id: str
    doctor: str | None = None
    unit_id: str
    unit: str | None = None
    starts_at: datetime
    ends_at: datetime
    status: str
    reason: str


class SlotDoctorView(StrictModel):
    id: str
    name: str
    crm: str


class SlotUnitView(StrictModel):
    id: str
    name: str
    address: str


class AvailabilitySlotView(StrictModel):
    id: str
    doctor: SlotDoctorView
    unit: SlotUnitView
    starts_at: datetime
    ends_at: datetime
    timezone: str


class AvailabilityPage(StrictModel):
    items: list[AvailabilitySlotView]
    total: int
    page: int = 1
    page_size: int
    timezone: str


class AvailabilityRulePayload(StrictModel):
    doctor_id: str
    unit_id: str
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time
    slot_minutes: int = Field(default=30, ge=10, le=240)
    valid_from: date | None = None
    valid_until: date | None = None
    active: bool = True


class AvailabilityBlockPayload(StrictModel):
    doctor_id: str
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(default="Bloqueio administrativo", max_length=200)


class AvailabilityRuleView(AvailabilityRulePayload):
    id: str


class AvailabilityBlockView(AvailabilityBlockPayload):
    id: str


class DashboardView(StrictModel):
    appointments_today: int
    confirmed_today: int
    patients: int
    knowledge_pending: int


class PatientListView(StrictModel):
    id: str
    name: str
    cpf: str
    birth_date: date | None
    email: str
    created_at: datetime
