from __future__ import annotations

import re
import unicodedata

from app.modules.knowledge.application.chunking import (
    GLUED_HEADING_REPLACEMENTS,
    normalize_extracted_text,
)

STOP_WORDS = {
    "a",
    "ao",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "no",
    "o",
    "os",
    "para",
    "por",
    "qual",
    "que",
    "um",
    "uma",
    "voces",
}
DISPLAY_PREFIXES = (
    "Diretrizes para coleta uso armazenamento compartilhamento e proteção de dados ",
    "Orientação ao paciente sobre etapas prazos e acesso aos resultados ",
)


def relevant_excerpt(question: str, content: str, limit: int = 420) -> str:
    terms = _terms(question)
    candidates: list[tuple[int, int, str]] = []
    for position, segment in enumerate(_segments(content)):
        if not _is_readable(segment):
            continue
        overlap = len(terms & _terms(segment))
        candidates.append((overlap, -position, segment))
    if not candidates:
        return ""

    candidates.sort(reverse=True)
    selected = [candidates[0][2]]
    for overlap, _, segment in candidates[1:]:
        if overlap <= 0 or len(" ".join(selected + [segment])) > limit:
            continue
        selected.append(segment)
        if len(selected) == 2:
            break
    excerpt = " ".join(selected).strip()
    if excerpt and excerpt[-1] not in ".!?":
        excerpt += "."
    return excerpt[:limit].rstrip()


def _segments(content: str) -> list[str]:
    normalized = normalize_extracted_text(content)
    normalized = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", normalized)
    normalized = normalized.replace("•", "\n")
    return [
        _clean_segment(part) for part in re.split(r"\n+|(?<=[.!?])\s+", normalized) if part.strip()
    ]


def _clean_segment(value: str) -> str:
    segment = " ".join(value.split()).strip(" -|:")
    for prefix in DISPLAY_PREFIXES:
        if segment.casefold().startswith(prefix.casefold()):
            return segment[len(prefix) :].lstrip()
    return segment


def _is_readable(segment: str) -> bool:
    lowered = segment.casefold()
    known_headings = {heading.casefold() for heading in GLUED_HEADING_REPLACEMENTS.values()}
    if (
        len(segment) < 18
        or lowered.startswith("documento institucional")
        or lowered in known_headings
    ):
        return False
    words = segment.split()
    return len(words) >= 4 and not any(len(word) >= 28 for word in words)


def _terms(value: str) -> set[str]:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return {
        token
        for token in re.findall(r"[a-z0-9]+", plain)
        if len(token) >= 3 and token not in STOP_WORDS
    }
