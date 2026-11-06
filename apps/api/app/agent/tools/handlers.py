from __future__ import annotations

from datetime import timedelta

from app.agent.tools.models import (
    AppointmentsResult,
    AvailabilityArguments,
    AvailabilityResult,
    CancelAppointmentArguments,
    CreateAppointmentArguments,
    DirectoryResult,
    EmptyArguments,
    ExamsResult,
    InsurersResult,
    KnowledgeArguments,
    KnowledgeResult,
    SearchDirectoryArguments,
    SpecialtiesResult,
    ToolArguments,
    UnitsResult,
)
from app.agent.tools.registry import ToolRisk, ToolSpec
from app.modules.catalog.application import CatalogService
from app.modules.catalog.domain import CatalogKind
from app.modules.identity.domain import Actor
from app.modules.knowledge.application import KnowledgeService
from app.modules.knowledge.domain.models import Answerability
from app.modules.scheduling.application import SchedulingService
from app.shared.application import AuthenticationRequiredError


class CatalogHandler:
    arguments_model = EmptyArguments

    def __init__(self, kind: CatalogKind, result_type: str):
        self.kind, self.result_type = kind, result_type

    def execute(self, arguments: ToolArguments, actor: Actor | None):
        result = CatalogService().list_catalog(self.kind)
        models = {
            "insurers": InsurersResult,
            "exams": ExamsResult,
            "specialties": SpecialtiesResult,
            "units": UnitsResult,
        }
        return models[self.result_type](items=result["items"], total=result["total"])


class DirectoryHandler:
    arguments_model = SearchDirectoryArguments

    def execute(self, arguments: SearchDirectoryArguments, actor: Actor | None):
        result = CatalogService().list_doctors(arguments.query)
        return DirectoryResult(items=result["items"], total=result["total"])


class AvailabilityHandler:
    arguments_model = AvailabilityArguments

    def execute(self, arguments: AvailabilityArguments, actor: Actor | None):
        result = SchedulingService().availability(
            arguments.from_date,
            arguments.to_date or arguments.from_date + timedelta(days=14),
            arguments.doctor_id,
            arguments.specialty_id,
            arguments.unit_id,
            arguments.insurer_id,
            arguments.period,
        )
        return AvailabilityResult(
            items=result["items"], total=result["total"], timezone=result["timezone"]
        )


class AppointmentsHandler:
    arguments_model = EmptyArguments

    def execute(self, arguments: EmptyArguments, actor: Actor | None):
        if actor is None:
            raise AuthenticationRequiredError("Identificação necessária")
        result = SchedulingService().list_mine(actor)
        return AppointmentsResult(items=result["items"], total=result["total"])


class KnowledgeHandler:
    arguments_model = KnowledgeArguments

    def execute(self, arguments: KnowledgeArguments, actor: Actor | None):
        result = KnowledgeService().retrieve(arguments.query)
        citations = [
            {"title": item.title, "source": item.source, "excerpt": item.content[:240]}
            for item in result.evidence
        ]
        confidence = result.confidence if result.answerability == Answerability.SUPPORTED else 0
        return KnowledgeResult(citations=citations, confidence=confidence)


class CreateAppointmentHandler:
    arguments_model = CreateAppointmentArguments

    def execute(self, arguments: CreateAppointmentArguments, actor: Actor | None):
        if actor is None:
            raise AuthenticationRequiredError("Identificação necessária")
        from app.agent.tools.models import AppointmentResult

        item = SchedulingService().create(
            actor, arguments.doctor_id, arguments.starts_at, arguments.reason
        )
        return AppointmentResult(type="appointment_created", appointment=item)


class CancelAppointmentHandler:
    arguments_model = CancelAppointmentArguments

    def execute(self, arguments: CancelAppointmentArguments, actor: Actor | None):
        if actor is None:
            raise AuthenticationRequiredError("Identificação necessária")
        from app.agent.tools.models import AppointmentResult

        item = SchedulingService().cancel(actor, arguments.appointment_id)
        return AppointmentResult(type="appointment_cancelled", appointment=item)


def tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            "list_insurers",
            "Lista convênios ativos.",
            ToolRisk.READ,
            CatalogHandler(CatalogKind.INSURER, "insurers"),
        ),
        ToolSpec(
            "list_exams",
            "Lista exames ativos.",
            ToolRisk.READ,
            CatalogHandler(CatalogKind.EXAM, "exams"),
        ),
        ToolSpec(
            "list_specialties",
            "Lista especialidades ativas.",
            ToolRisk.READ,
            CatalogHandler(CatalogKind.SPECIALTY, "specialties"),
        ),
        ToolSpec(
            "list_units",
            "Lista unidades ativas.",
            ToolRisk.READ,
            CatalogHandler(CatalogKind.UNIT, "units"),
        ),
        ToolSpec("search_directory", "Pesquisa profissionais.", ToolRisk.READ, DirectoryHandler()),
        ToolSpec(
            "search_availability", "Pesquisa horários reais.", ToolRisk.READ, AvailabilityHandler()
        ),
        ToolSpec(
            "search_knowledge", "Pesquisa conhecimento aprovado.", ToolRisk.READ, KnowledgeHandler()
        ),
        ToolSpec(
            "list_my_appointments",
            "Lista consultas do paciente.",
            ToolRisk.SENSITIVE,
            AppointmentsHandler(),
            True,
        ),
        ToolSpec(
            "create_appointment",
            "Agenda uma consulta.",
            ToolRisk.WRITE,
            CreateAppointmentHandler(),
            True,
            True,
        ),
        ToolSpec(
            "cancel_appointment",
            "Cancela uma consulta.",
            ToolRisk.WRITE,
            CancelAppointmentHandler(),
            True,
            True,
        ),
    )
