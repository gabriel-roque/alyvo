from __future__ import annotations

from app.agent.presentation.knowledge import relevant_excerpt
from app.agent.routing.rules import normalize
from app.agent.tools.models import AppointmentResult
from app.modules.knowledge.application import KnowledgeService
from app.modules.knowledge.domain.models import Answerability


def post_appointment_guidance(result: AppointmentResult) -> tuple[str, list[dict[str, str]]]:
    """Return only guidance demonstrably applicable to the confirmed appointment."""

    appointment = result.appointment
    doctor = appointment.doctor or ""
    unit = appointment.unit or ""
    question = f"Orientações para a consulta com {doctor} na {unit}"
    retrieved = KnowledgeService().retrieve(question)
    if retrieved.answerability != Answerability.SUPPORTED:
        return "", []
    citations: list[dict[str, str]] = []
    for evidence in retrieved.evidence:
        if not _applies(evidence.content, doctor, unit):
            continue
        excerpt = relevant_excerpt(question, evidence.content)
        if excerpt:
            citations.append(
                {
                    "title": evidence.title,
                    "source": evidence.source,
                    "excerpt": excerpt,
                }
            )
        if len(citations) == 2:
            break
    if not citations:
        return "", []
    guidance = " ".join(citation["excerpt"] for citation in citations)
    return f" Orientações para este atendimento: {guidance}", citations


def _applies(content: str, doctor: str, unit: str) -> bool:
    text = normalize(content)
    doctor_tokens = [token for token in normalize(doctor).split() if len(token) >= 4]
    unit_tokens = [token for token in normalize(unit).split() if len(token) >= 4]
    doctor_match = bool(doctor_tokens) and all(token in text for token in doctor_tokens)
    unit_match = bool(unit_tokens) and all(token in text for token in unit_tokens)
    guidance = any(
        term in text
        for term in ("orientacao", "antecedencia", "ordem de chegada", "comparecer", "chegar")
    )
    return guidance and (doctor_match or unit_match)
