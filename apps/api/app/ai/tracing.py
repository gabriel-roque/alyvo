from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SAFE_TOOL_NAMES = {
    "cancel_appointment",
    "create_appointment",
    "list_exams",
    "list_insurers",
    "list_my_appointments",
    "list_specialties",
    "list_units",
    "search_availability",
    "search_directory",
    "search_knowledge",
}
SAFE_ARGUMENT_KEYS = {
    "appointment_id",
    "doctor",
    "doctor_id",
    "from",
    "include_address",
    "insurer",
    "offset",
    "period",
    "query",
    "reason",
    "refinement",
    "specialty",
    "starts_at",
    "status",
    "to",
    "unit",
}
SAFE_RESULT_TYPES = {
    "appointment_cancelled",
    "appointment_created",
    "appointments",
    "availability",
    "directory",
    "exams",
    "insurers",
    "specialties",
    "units",
}


def _mapping(value: Any) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def tool_span_inputs(inputs: dict) -> dict:
    """Keep tool spans useful without exporting arguments or runtime identity."""
    arguments = _mapping(inputs.get("arguments"))
    argument_keys = {str(key) for key in arguments}
    return {
        "tool_name": _allow(inputs.get("name"), SAFE_TOOL_NAMES),
        "argument_keys": sorted(argument_keys & SAFE_ARGUMENT_KEYS),
        "unknown_argument_count": len(argument_keys - SAFE_ARGUMENT_KEYS),
        "authenticated": bool(inputs.get("identity")),
    }


def tool_span_outputs(output: Any) -> dict:
    result = _mapping(output)
    tool_result = _mapping(result.get("tool_result"))
    items = tool_result.get("items")
    return {
        "status": "ok",
        "intent": _allow(result.get("intent"), SAFE_TOOL_NAMES),
        "confidence": result.get("confidence"),
        "result_type": _allow(tool_result.get("type"), SAFE_RESULT_TYPES, default=None),
        "result_count": len(items) if isinstance(items, list) else None,
        "auth_required": bool(result.get("auth_required")),
    }


def retrieval_span_inputs(inputs: dict) -> dict:
    """Never send the query, tenant, database session, or store to LangSmith."""
    question = inputs.get("question")
    return {
        "query_present": isinstance(question, str) and bool(question.strip()),
        "query_length_bucket": _length_bucket(question),
    }


def retrieval_span_outputs(output: Any) -> dict:
    if hasattr(output, "confidence") and hasattr(output, "strategy"):
        contexts = getattr(output, "answer_context", ())
        return {
            "status": "ok",
            "strategy": getattr(output, "strategy", "unknown"),
            "result_count": len(contexts),
            "confidence": getattr(output, "confidence", None),
        }
    if isinstance(output, list):
        return {"status": "ok", "result_count": len(output)}
    return {"status": "ok", "result_count": 0}


def _length_bucket(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "empty"
    length = len(value)
    if length <= 32:
        return "1-32"
    if length <= 128:
        return "33-128"
    return "129+"


def _allow(value: Any, allowed: set[str], *, default: str | None = "unknown"):
    return value if isinstance(value, str) and value in allowed else default
