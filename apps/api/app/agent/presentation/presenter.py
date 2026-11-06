from __future__ import annotations

from typing import Any

from app.agent.tools.models import ToolResult


def response(answer: str, intent: str, **values: Any) -> dict[str, Any]:
    return {
        "answer": answer,
        "intent": intent,
        "confidence": values.pop("confidence", 1.0),
        "citations": values.pop("citations", []),
        "auth_required": values.pop("auth_required", False),
        "confirmation_request": values.pop("confirmation_request", None),
        "tool_result": values.pop("tool_result", None),
        "tool_call": {"name": intent},
        "suggestions": values.pop("suggestions", []),
        **values,
    }


def present_tool_result(name: str, result: ToolResult) -> dict[str, Any]:
    payload = result.model_dump(mode="json")
    if payload["type"] == "knowledge":
        answer = "Com base no conhecimento aprovado da clínica: " + (
            payload["citations"][0]["excerpt"]
            if payload["citations"]
            else "não encontrei evidência suficiente."
        )
        return response(
            answer,
            name,
            tool_result=payload,
            citations=payload["citations"],
            confidence=payload["confidence"],
        )
    answer = f"Encontrei {payload.get('total', 1)} resultado(s)."
    if payload["type"] == "appointment_created":
        answer = "Consulta agendada com sucesso."
    elif payload["type"] == "appointment_cancelled":
        answer = "Consulta cancelada com sucesso."
    return response(answer, name, tool_result=payload)
