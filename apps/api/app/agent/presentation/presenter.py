from __future__ import annotations

from datetime import date
from typing import Any

from app.agent.routing.rules import normalize
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
        return _present_knowledge(name, payload)
    if payload["type"] == "availability":
        return _present_availability(name, payload)
    return _present_standard(name, payload)


def _present_knowledge(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not payload["citations"] or payload["confidence"] <= 0:
        return response(
            "Não encontrei essa informação com segurança na base da clínica. Posso tentar ajudar se você reformular a pergunta ou procurar outro assunto.",
            name,
            tool_result=payload,
            confidence=0,
            suggestions=[
                {"label": "Horário da clínica", "message": "Qual é o horário da clínica?"},
                {"label": "Falar sobre agenda", "message": "Quero ver horários disponíveis"},
            ],
        )
    excerpt = payload["citations"][0]["excerpt"]
    question = normalize(payload["query"])
    if "fim de semana" in question or "finais de semana" in question:
        answer = (
            "Pelo horário informado pela clínica, não há atendimento regular aos finais de "
            f"semana. {excerpt}"
        )
    else:
        answer = f"Claro. Segundo as informações da clínica: {excerpt}"
    return response(
        answer,
        name,
        tool_result=payload,
        citations=payload["citations"],
        confidence=payload["confidence"],
    )


def _present_availability(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    day = _human_date(date.fromisoformat(payload["requested_from"]))
    period = _period_label(payload.get("period"))
    if not payload["items"]:
        return response(
            f"Não encontrei horários disponíveis para {day}{period}. Quer tentar outro dia?",
            name,
            tool_result=payload,
            suggestions=[
                {"label": "Tentar amanhã", "message": "Quero horários para amanhã"},
                {
                    "label": "Próxima sexta-feira",
                    "message": "Quero horários na próxima sexta-feira",
                },
            ],
        )
    shown = len(payload["items"])
    suffix = "" if payload["total"] == shown else f" Mostrei as {shown} primeiras opções."
    return response(
        f"Perfeito! Encontrei horários para {day}{period}.{suffix} Qual deles funciona melhor para você?",
        name,
        tool_result=payload,
    )


def _present_standard(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if payload["type"] == "directory":
        answer = (
            "Encontrei estes profissionais para você:"
            if payload["items"]
            else "Não encontrei um profissional com esses critérios. Quer tentar outra especialidade ou convênio?"
        )
    elif payload["type"] in {"insurers", "exams", "specialties", "units"}:
        answer = (
            "Separei estas opções para você:"
            if payload["items"]
            else "Não encontrei opções disponíveis no momento."
        )
    elif payload["type"] == "appointments":
        answer = (
            "Estas são as suas consultas:"
            if payload["items"]
            else "Você não possui consultas agendadas no momento."
        )
    elif payload["type"] == "appointment_created":
        answer = "Consulta agendada com sucesso."
    elif payload["type"] == "appointment_cancelled":
        answer = "Consulta cancelada com sucesso."
    return response(answer, name, tool_result=payload)


WEEKDAYS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)
MONTHS = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def _human_date(value: date) -> str:
    return f"{WEEKDAYS[value.weekday()]}, {value.day} de {MONTHS[value.month - 1]}"


def _period_label(period: str | None) -> str:
    labels = {"morning": " pela manhã", "afternoon": " à tarde", "evening": " à noite"}
    return labels.get(period, "")
