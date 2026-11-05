from __future__ import annotations

import re

SENSITIVE_PATTERNS = (
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[CPF]"),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[/-](?:0?[1-9]|1[0-2])[/-](?:19|20)\d{2}\b"), "[DATA]"),
    (re.compile(r"(?i)bearer\s+[a-z0-9._~-]+"), "Bearer [TOKEN]"),
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def safe_trace_metadata(classification: dict | None, **extra) -> dict:
    classification = classification or {}
    allowed = {
        "domain": classification.get("domain"),
        "action": classification.get("action"),
        "topic": classification.get("topic"),
        "risk_level": classification.get("risk_level"),
        "confidence": classification.get("confidence"),
        **extra,
    }
    return {key: value for key, value in allowed.items() if value is not None}
