from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyArguments(ToolArguments):
    pass


class SearchDirectoryArguments(ToolArguments):
    query: str = ""


class AvailabilityArguments(ToolArguments):
    from_date: date
    to_date: date | None = None
    doctor_id: str | None = None
    specialty_id: str | None = None
    unit_id: str | None = None
    insurer_id: str | None = None
    period: Literal["morning", "afternoon", "evening"] | None = None


class KnowledgeArguments(ToolArguments):
    query: str = Field(min_length=1, max_length=4000)


class CreateAppointmentArguments(ToolArguments):
    doctor_id: str
    starts_at: datetime
    reason: str = Field(default="Consulta", max_length=200)


class CancelAppointmentArguments(ToolArguments):
    appointment_id: str


class ToolResultBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogItem(ToolResultBase):
    id: str
    name: str
    active: bool
    description: str | None = None
    address: str | None = None
    preparation: str | None = None
    unit_ids: list[str] = Field(default_factory=list)


class DirectoryItem(ToolResultBase):
    id: str
    name: str
    crm: str
    specialty_id: str
    specialty: str
    unit_id: str
    unit: str
    insurer_ids: list[str]
    insurers: list[str]
    active: bool


class NamedItem(ToolResultBase):
    id: str
    name: str
    crm: str | None = None
    address: str | None = None


class AvailabilityItem(ToolResultBase):
    id: str
    doctor: NamedItem
    unit: NamedItem
    starts_at: datetime
    ends_at: datetime
    timezone: str


class AppointmentItem(ToolResultBase):
    id: str
    patient_id: str
    doctor_id: str
    doctor: str | None
    unit_id: str
    unit: str | None
    starts_at: datetime
    ends_at: datetime
    status: str
    reason: str


class InsurersResult(ToolResultBase):
    type: Literal["insurers"] = "insurers"
    items: list[CatalogItem]
    total: int


class ExamsResult(ToolResultBase):
    type: Literal["exams"] = "exams"
    items: list[CatalogItem]
    total: int


class SpecialtiesResult(ToolResultBase):
    type: Literal["specialties"] = "specialties"
    items: list[CatalogItem]
    total: int


class UnitsResult(ToolResultBase):
    type: Literal["units"] = "units"
    items: list[CatalogItem]
    total: int


class DirectoryResult(ToolResultBase):
    type: Literal["directory"] = "directory"
    items: list[DirectoryItem]
    total: int


class AvailabilityResult(ToolResultBase):
    type: Literal["availability"] = "availability"
    items: list[AvailabilityItem]
    total: int
    timezone: str | None = None


class AppointmentsResult(ToolResultBase):
    type: Literal["appointments"] = "appointments"
    items: list[AppointmentItem]
    total: int


class KnowledgeResult(ToolResultBase):
    type: Literal["knowledge"] = "knowledge"
    citations: list[dict[str, str]]
    confidence: float


class AppointmentResult(ToolResultBase):
    type: Literal["appointment_created", "appointment_cancelled"]
    appointment: AppointmentItem


ToolResult = Annotated[
    InsurersResult
    | ExamsResult
    | SpecialtiesResult
    | UnitsResult
    | DirectoryResult
    | AvailabilityResult
    | AppointmentsResult
    | KnowledgeResult
    | AppointmentResult,
    Field(discriminator="type"),
]

ToolArgumentsUnion = (
    EmptyArguments
    | SearchDirectoryArguments
    | AvailabilityArguments
    | KnowledgeArguments
    | CreateAppointmentArguments
    | CancelAppointmentArguments
)
