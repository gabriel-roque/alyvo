from __future__ import annotations

from dataclasses import dataclass

from app.agent.routing import Action, Domain, Topic


@dataclass(frozen=True)
class Capability:
    name: str
    domain: Domain
    action: Action
    topic: Topic
    tool_name: str


class CapabilityRegistry:
    """Declarative boundary between language interpretation and executable tools."""

    def __init__(self, capabilities: tuple[Capability, ...] | None = None) -> None:
        values = capabilities or default_capabilities()
        self._items = {(item.domain, item.action, item.topic): item for item in values}

    def resolve(self, domain: Domain, action: Action, topic: Topic) -> Capability | None:
        exact = self._items.get((domain, action, topic))
        if exact is not None:
            return exact
        return next(
            (
                item
                for item in self._items.values()
                if item.domain == domain and item.topic == topic
            ),
            None,
        )


def default_capabilities() -> tuple[Capability, ...]:
    return (
        Capability(
            "directory.search", Domain.DIRECTORY, Action.SEARCH, Topic.DOCTOR, "search_directory"
        ),
        Capability("insurers.list", Domain.DIRECTORY, Action.LIST, Topic.INSURER, "list_insurers"),
        Capability(
            "specialties.list", Domain.DIRECTORY, Action.LIST, Topic.SPECIALTY, "list_specialties"
        ),
        Capability("units.list", Domain.DIRECTORY, Action.LIST, Topic.UNIT, "list_units"),
        Capability("exams.list", Domain.DIRECTORY, Action.LIST, Topic.EXAM, "list_exams"),
        Capability(
            "appointments.list",
            Domain.PATIENT,
            Action.LIST,
            Topic.OWN_APPOINTMENT,
            "list_my_appointments",
        ),
        Capability(
            "appointments.reschedule",
            Domain.SCHEDULING,
            Action.RESCHEDULE,
            Topic.OWN_APPOINTMENT,
            "list_my_appointments",
        ),
        Capability(
            "knowledge.search",
            Domain.KNOWLEDGE,
            Action.SEARCH,
            Topic.INSTITUTIONAL,
            "search_knowledge",
        ),
    )
