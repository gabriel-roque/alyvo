from __future__ import annotations

from enum import StrEnum

from app.agent.tools.registry import ToolSpec
from app.modules.identity.domain import Actor


class ToolGate(StrEnum):
    EXECUTE = "execute"
    AUTHENTICATE = "authenticate"
    CONFIRM = "confirm"


class ToolInvocationPolicy:
    def evaluate(
        self,
        spec: ToolSpec,
        actor: Actor | None,
        *,
        confirmed: bool = False,
    ) -> ToolGate:
        if spec.requires_authentication and actor is None:
            return ToolGate.AUTHENTICATE
        if spec.requires_confirmation and not confirmed:
            return ToolGate.CONFIRM
        return ToolGate.EXECUTE
