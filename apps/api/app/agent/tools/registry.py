from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.agent.tools.models import ToolArguments, ToolResult
from app.modules.identity.domain import Actor


class ToolRisk(StrEnum):
    READ = "read"
    SENSITIVE = "sensitive"
    WRITE = "write"


class ToolHandler(Protocol):
    arguments_model: type[ToolArguments]

    def execute(self, arguments: ToolArguments, actor: Actor | None) -> ToolResult: ...


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    risk: ToolRisk
    handler: ToolHandler
    requires_authentication: bool = False
    requires_confirmation: bool = False


class ToolRegistry:
    def __init__(self, specs: tuple[ToolSpec, ...]):
        self._specs = {spec.name: spec for spec in specs}

    def get(self, name: str) -> ToolSpec:
        return self._specs[name]

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs.values())

    def provider_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.handler.arguments_model.model_json_schema(),
                },
            }
            for spec in self._specs.values()
        ]


def build_tool_registry() -> ToolRegistry:
    from app.agent.tools.handlers import tool_specs

    return ToolRegistry(tool_specs())
