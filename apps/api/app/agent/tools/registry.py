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
    idempotent: bool = True
    timeout_seconds: float = 5.0
    audit: bool = False


class ToolRegistry:
    def __init__(self, specs: tuple[ToolSpec, ...]):
        self._validate_specs(specs)
        self._specs = {spec.name: spec for spec in specs}

    @staticmethod
    def _validate_specs(specs: tuple[ToolSpec, ...]) -> None:
        names = [spec.name for spec in specs]
        if len(names) != len(set(names)):
            raise ValueError("ToolRegistry não permite nomes duplicados")
        for spec in specs:
            if spec.timeout_seconds <= 0:
                raise ValueError(f"Timeout inválido para tool {spec.name}")
            if spec.risk == ToolRisk.SENSITIVE and not spec.requires_authentication:
                raise ValueError(f"Tool sensível {spec.name} exige autenticação")
            if spec.risk == ToolRisk.WRITE and not (
                spec.requires_authentication and spec.requires_confirmation
            ):
                raise ValueError(f"Tool de escrita {spec.name} exige autenticação e confirmação")

    def get(self, name: str) -> ToolSpec:
        return self._specs[name]

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs.values())

    def provider_tools(self) -> list[dict[str, object]]:
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
