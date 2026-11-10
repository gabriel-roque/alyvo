from __future__ import annotations

import re
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
    iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", message)
    if iso:
        try:
            value = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
        return value, value

    local = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(20\d{2}))?\b", message)
    if local:
        year = int(local.group(3) or today.year)
        try:
            value = date(year, int(local.group(2)), int(local.group(1)))
        except ValueError:
            return None
        if local.group(3) is None and value < today:
            value = value.replace(year=year + 1)
        return value, value
    return None


def _relative_date(text: str, today: date) -> tuple[date, date] | None:
    if "depois de amanha" in text:
        value = today + timedelta(days=2)
        return value, value
    if "amanha" in text:
        value = today + timedelta(days=1)
        return value, value
    if "hoje" in text:
        return today, today
    if "proxima semana" in text:
        monday = today + timedelta(days=(7 - today.weekday()))
        return monday, monday + timedelta(days=4)
    if "esta semana" in text or "essa semana" in text:
        return today, today + timedelta(days=max(6 - today.weekday(), 0))
    for label, weekday in WEEKDAYS.items():
        if label in text:
            offset = (weekday - today.weekday()) % 7
            if "proxima" in text and offset == 0:
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
