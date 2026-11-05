from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class EmptyArguments(ToolArguments):
    pass


class ListExamsArguments(ToolArguments):
    unit: str | None = None


class DirectoryArguments(ToolArguments):
    specialty: str | None = None
    doctor: str | None = None
    unit: str | None = None
    insurer: str | None = None
    include_address: bool = False


class KnowledgeArguments(ToolArguments):
    query: str = Field(min_length=1, max_length=4000)


class AppointmentListArguments(ToolArguments):
    status: str | None = None


class AvailabilityArguments(DirectoryArguments):
    period: str | None = None
    from_date: date | None = Field(default=None, alias="from")
    to: date | None = None
    offset: int = Field(default=0, ge=0)
    refinement: bool = False


class CreateAppointmentArguments(ToolArguments):
    doctor_id: str
    starts_at: datetime
    reason: str = Field(default="Consulta", max_length=200)


class CancelAppointmentArguments(ToolArguments):
    appointment_id: str


class ToolRisk(StrEnum):
    READ = "read"
    SENSITIVE = "sensitive"
    WRITE = "write"


class ToolSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    description: str
    arguments_model: type[ToolArguments]
    risk: ToolRisk
    requires_authentication: bool = False
    requires_confirmation: bool = False


def _spec(
    name: str,
    description: str,
    arguments_model: type[ToolArguments],
    risk: ToolRisk = ToolRisk.READ,
    *,
    authentication: bool = False,
    confirmation: bool = False,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        arguments_model=arguments_model,
        risk=risk,
        requires_authentication=authentication,
        requires_confirmation=confirmation,
    )


TOOL_REGISTRY = {
    item.name: item
    for item in (
        _spec("list_insurers", "Lista convênios ativos.", EmptyArguments),
        _spec("list_exams", "Lista exames cadastrados.", ListExamsArguments),
        _spec("list_specialties", "Lista especialidades ativas.", EmptyArguments),
        _spec("list_units", "Lista unidades e endereços.", EmptyArguments),
        _spec("search_directory", "Pesquisa o diretório aprovado.", DirectoryArguments),
        _spec("search_knowledge", "Pesquisa políticas aprovadas.", KnowledgeArguments),
        _spec(
            "list_my_appointments",
            "Lista consultas do paciente.",
            AppointmentListArguments,
            ToolRisk.SENSITIVE,
            authentication=True,
        ),
        _spec("search_availability", "Pesquisa horários reais.", AvailabilityArguments),
        _spec(
            "create_appointment",
            "Cria uma consulta confirmada.",
            CreateAppointmentArguments,
            ToolRisk.WRITE,
            authentication=True,
            confirmation=True,
        ),
        _spec(
            "cancel_appointment",
            "Cancela uma consulta do paciente.",
            CancelAppointmentArguments,
            ToolRisk.WRITE,
            authentication=True,
            confirmation=True,
        ),
    )
}


def provider_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.arguments_model.model_json_schema(),
            },
        }
        for spec in TOOL_REGISTRY.values()
    ]


def validate_tool_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    spec = TOOL_REGISTRY[name]
    return spec.arguments_model.model_validate(arguments).model_dump(
        by_alias=True,
        exclude_none=True,
        mode="json",
    )
