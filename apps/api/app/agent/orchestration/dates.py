from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, timedelta

from app.agent.conversation import AvailabilitySlots
from app.agent.routing.rules import normalize

WEEKDAYS = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "domingo": 6,
}

MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

DAY_WORDS = {
    "primeiro": 1,
    "um": 1,
    "dois": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "quatorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
    "vinte e um": 21,
    "vinte e dois": 22,
    "vinte e tres": 23,
    "vinte e quatro": 24,
    "vinte e cinco": 25,
    "vinte e seis": 26,
    "vinte e sete": 27,
    "vinte e oito": 28,
    "vinte e nove": 29,
    "trinta": 30,
    "trinta e um": 31,
}


def parse_availability_request(message: str, today: date) -> dict[str, str | None] | None:
    slots = extract_availability_slots(message, today)
    if slots.from_date is None:
        return None
    return slots.tool_arguments()


def extract_availability_slots(message: str, today: date) -> AvailabilitySlots:
    text = normalize(message)
    requested = _explicit_date(message, today) or _relative_date(text, today)
    if requested is None:
        return AvailabilitySlots(period=_period(text))
    start, end = requested
    return AvailabilitySlots(from_date=start, to_date=end, period=_period(text))


def _explicit_date(message: str, today: date) -> tuple[date, date] | None:
    parsers = (_iso_date, _local_date, _named_date, _bare_day_date)
    for parser in parsers:
        if result := parser(message, today):
            return result
    return None


def _iso_date(message: str, today: date) -> tuple[date, date] | None:
    iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", message)
    if not iso:
        return None
    value = _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    return (value, value) if value else None


def _local_date(message: str, today: date) -> tuple[date, date] | None:
    local = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(20\d{2}))?\b", message)
    if not local:
        return None
    year = int(local.group(3) or today.year)
    value = _safe_date(year, int(local.group(2)), int(local.group(1)))
    if value is None:
        return None
    if local.group(3) is None and value < today:
        value = _next_valid_year(year, value.month, value.day)
    return (value, value) if value else None


def _named_date(message: str, today: date) -> tuple[date, date] | None:
    text = normalize(message)
    month_names = "|".join(MONTHS)
    named = re.search(
        rf"\b(\d{{1,2}})\s+de\s+({month_names})(?:\s+de\s+(20\d{{2}}))?\b",
        text,
    )
    if not named:
        return None
    month = MONTHS[named.group(2)]
    year = int(named.group(3) or today.year)
    value = _safe_date(year, month, int(named.group(1)))
    if value is None:
        return None
    if named.group(3) is None and value < today:
        value = _next_valid_year(year, value.month, value.day)
    return (value, value) if value else None


def _bare_day_date(message: str, today: date) -> tuple[date, date] | None:
    text = normalize(message)
    bare_day = re.search(r"\bdia\s+(\d{1,2})\b", text)
    if bare_day:
        value = _next_day_of_month(today, int(bare_day.group(1)))
        return (value, value) if value else None

    for label, day in sorted(DAY_WORDS.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\bdia\s+{re.escape(label)}\b", text):
            value = _next_day_of_month(today, day)
            return (value, value) if value else None
    return None


def _relative_date(text: str, today: date) -> tuple[date, date] | None:
    return (
        _fixed_relative_date(text, today)
        or _relative_weeks_date(text, today)
        or _relative_weekday_date(text, today)
    )


def _fixed_relative_date(text: str, today: date) -> tuple[date, date] | None:
    if "depois de amanha" in text:
        value = today + timedelta(days=2)
        return value, value
    if "amanha" in text:
        value = today + timedelta(days=1)
        return value, value
    if "hoje" in text:
        return today, today
    if "proxima semana" in text or "semana que vem" in text:
        monday = today + timedelta(days=(7 - today.weekday()))
        return monday, monday + timedelta(days=4)
    if "esta semana" in text or "essa semana" in text:
        return today, today + timedelta(days=max(6 - today.weekday(), 0))
    if "fim do mes" in text or "final do mes" in text:
        last = date(today.year, today.month, monthrange(today.year, today.month)[1])
        return max(today, last - timedelta(days=2)), last
    return None


def _relative_weeks_date(text: str, today: date) -> tuple[date, date] | None:
    weeks = re.search(r"\bdaqui a (\d+|uma|duas|tres) semanas?\b", text)
    if not weeks:
        return None
    amount = {"uma": 1, "duas": 2, "tres": 3}.get(weeks.group(1))
    amount = amount or int(weeks.group(1))
    value = today + timedelta(weeks=amount)
    return value, value


def _relative_weekday_date(text: str, today: date) -> tuple[date, date] | None:
    for label, weekday in WEEKDAYS.items():
        if label in text:
            offset = (weekday - today.weekday()) % 7
            if "outra" in text:
                offset += 7
            elif "proxima" in text and offset == 0:
                offset = 7
            value = today + timedelta(days=offset)
            return value, value
    return None


def _period(text: str) -> str | None:
    if "manha" in text:
        return "morning"
    if "tarde" in text:
        return "afternoon"
    if "noite" in text:
        return "evening"
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _next_day_of_month(today: date, day: int) -> date | None:
    value = _safe_date(today.year, today.month, day)
    if value is not None and value >= today:
        return value
    next_month = 1 if today.month == 12 else today.month + 1
    next_year = today.year + 1 if today.month == 12 else today.year
    return _safe_date(next_year, next_month, day)


def _next_valid_year(year: int, month: int, day: int) -> date | None:
    for candidate_year in range(year + 1, year + 9):
        if value := _safe_date(candidate_year, month, day):
            return value
    return None
