from __future__ import annotations

import re
import unicodedata

from app.shared.infrastructure.models import Doctor


def filter_doctors(doctors: list[Doctor], query: str) -> list[Doctor]:
    """Filter only by entities present in the catalog, never by conversational glue."""

    recognized = recognized_entity_ids(doctors, query)
    doctor_ids = set(recognized["doctor_ids"])
    specialties = set(recognized["specialty_ids"])
    units = set(recognized["unit_ids"])
    insurers = set(recognized["insurer_ids"])
    if not any((doctor_ids, specialties, units, insurers)):
        return doctors
    return [
        doctor
        for doctor in doctors
        if (not doctor_ids or doctor.id in doctor_ids)
        and (not specialties or doctor.specialty_id in specialties)
        and (not units or doctor.unit_id in units)
        and (not insurers or any(insurer.id in insurers for insurer in doctor.insurers))
    ]


def recognized_entity_ids(doctors: list[Doctor], query: str) -> dict[str, list[str]]:
    query_tokens = _search_tokens(query)
    return {
        "doctor_ids": sorted(
            doctor.id for doctor in doctors if _entity_is_mentioned(doctor.name, query_tokens)
        ),
        "specialty_ids": sorted(
            {
                doctor.specialty_id
                for doctor in doctors
                if _entity_or_root_is_mentioned(doctor.specialty.name, query_tokens)
            }
        ),
        "unit_ids": sorted(
            {
                doctor.unit_id
                for doctor in doctors
                if _entity_is_mentioned(doctor.unit.name, query_tokens)
            }
        ),
        "insurer_ids": sorted(
            {
                insurer.id
                for doctor in doctors
                for insurer in doctor.insurers
                if _entity_is_mentioned(insurer.name, query_tokens)
            }
        ),
    }


def _entity_or_root_is_mentioned(value: str, query_tokens: set[str]) -> bool:
    if _entity_is_mentioned(value, query_tokens):
        return True
    root = _semantic_root(value)
    return bool(root) and any(token.startswith(root) for token in query_tokens)


def _entity_is_mentioned(value: str, query_tokens: set[str]) -> bool:
    labels = {"dr", "dra", "doutor", "doutora", "unidade"}
    tokens = _search_tokens(value) - labels
    return bool(tokens) and all(
        any(
            candidate.startswith(token) or token.startswith(candidate) for candidate in query_tokens
        )
        for token in tokens
    )


def _semantic_root(value: str) -> str:
    tokens = _search_tokens(value)
    if len(tokens) != 1:
        return ""
    token = next(iter(tokens))
    for suffix in ("logia", "iatria", "ologia", "ia"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 5:
            return token[: -len(suffix)]
    return token[:7] if len(token) >= 7 else token


def _search_tokens(value: str) -> set[str]:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return {
        token[:8] if len(token) > 8 else token
        for token in re.findall(r"[a-z0-9]+", plain)
        if len(token) >= 3
    }
