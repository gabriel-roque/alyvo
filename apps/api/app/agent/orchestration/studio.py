"""LangGraph Studio entry point with deterministic synthetic adapters."""

from datetime import datetime, timedelta, timezone

from app.agent.orchestration.graph import AgentOrchestrator
from app.agent.tools import ToolRegistry, build_tool_registry
from app.agent.tools.models import (
    AppointmentResult,
    AppointmentsResult,
    AvailabilityResult,
    DirectoryResult,
    ExamsResult,
    InsurersResult,
    KnowledgeResult,
    SpecialtiesResult,
    UnitsResult,
)
from app.agent.tools.registry import ToolSpec


class SyntheticHandler:
    def __init__(self, name, arguments_model):
        self.name = name
        self.arguments_model = arguments_model

    def execute(self, arguments, actor):
        if self.name == "list_insurers":
            return InsurersResult(items=[], total=0)
        if self.name == "list_exams":
            return ExamsResult(items=[], total=0)
        if self.name == "list_specialties":
            return SpecialtiesResult(items=[], total=0)
        if self.name == "list_units":
            return UnitsResult(items=[], total=0)
        if self.name == "search_directory":
            return DirectoryResult(items=[], total=0)
        if self.name == "search_availability":
            return AvailabilityResult(items=[], total=0, timezone="America/Sao_Paulo")
        if self.name == "list_my_appointments":
            return AppointmentsResult(items=[], total=0)
        if self.name == "search_knowledge":
            return KnowledgeResult(citations=[], confidence=0)
        now = datetime.now(timezone.utc) + timedelta(days=1)
        result_type = (
            "appointment_created" if self.name == "create_appointment" else "appointment_cancelled"
        )
        return AppointmentResult(
            type=result_type,
            appointment={
                "id": "synthetic-appointment",
                "patient_id": "synthetic-patient",
                "doctor_id": "synthetic-doctor",
                "doctor": "Dra. Sintética",
                "unit_id": "synthetic-unit",
                "unit": "Unidade Sintética",
                "starts_at": now,
                "ends_at": now + timedelta(minutes=30),
                "status": "confirmed",
                "reason": "Consulta sintética",
            },
        )


def studio_registry() -> ToolRegistry:
    specs = tuple(
        ToolSpec(
            name=spec.name,
            description=spec.description,
            risk=spec.risk,
            handler=SyntheticHandler(spec.name, spec.handler.arguments_model),
            requires_authentication=spec.requires_authentication,
            requires_confirmation=spec.requires_confirmation,
        )
        for spec in build_tool_registry().specs()
    )
    return ToolRegistry(specs)


graph = AgentOrchestrator(tools=studio_registry()).graph
