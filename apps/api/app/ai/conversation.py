from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

WEEKDAYS = {
    "segunda": 0,
    "segunda feira": 0,
    "terca": 1,
    "terca feira": 1,
    "quarta": 2,
    "quarta feira": 2,
    "quinta": 3,
    "quinta feira": 3,
    "sexta": 4,
    "sexta feira": 4,
    "sabado": 5,
    "domingo": 6,
}
WEEKDAY_NAMES = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)
MONTH_NAMES = (
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


def normalized_text(value: str) -> str:
    value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9+/]+", " ", value).split())


class DateWindow(BaseModel):
    start: date
    end: date
    source: str
    explicit: bool = True


class DialogFilters(BaseModel):
    specialty: str | None = None
    doctor: str | None = None
    unit: str | None = None
    insurer: str | None = None
    period: Literal["morning", "afternoon", "evening"] | None = None
    start_date: date | None = None
    end_date: date | None = None


class DialogState(BaseModel):
    active_intent: str | None = None
    filters: DialogFilters = Field(default_factory=DialogFilters)
    last_options: list[dict] = Field(default_factory=list)
    recovery_attempts: int = 0
    last_entity: str | None = None
    availability_offset: int = 0


def tenant_timezone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "America/Sao_Paulo")
    except (KeyError, ValueError):
        return ZoneInfo("America/Sao_Paulo")


def tenant_today(timezone_name: str, now: datetime | None = None) -> date:
    zone = tenant_timezone(timezone_name)
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=zone)
    return instant.astimezone(zone).date()


def resolve_date_window(
    message: str,
    timezone_name: str = "America/Sao_Paulo",
    now: datetime | None = None,
) -> DateWindow | None:
    text = normalized_text(message)
    today = tenant_today(timezone_name, now)

    relative = (
        ("depois de amanha", 2),
        ("amanha", 1),
        ("hoje", 0),
    )
    for phrase, offset in relative:
        if phrase in text:
            target = today + timedelta(days=offset)
            return DateWindow(start=target, end=target, source=phrase)

    day_of_month = re.search(
        r"\b(?:dia\s+)?(\d{1,2})\s+(?:deste|desse|do)\s+(mes|proximo mes)\b",
        text,
    )
    if day_of_month:
        day = int(day_of_month.group(1))
        month_offset = 1 if "proximo" in day_of_month.group(2) else 0
        year = today.year + ((today.month + month_offset - 1) // 12)
        month = ((today.month + month_offset - 1) % 12) + 1
        try:
            target = date(year, month, day)
        except ValueError:
            return None
        return DateWindow(start=target, end=target, source=day_of_month.group(0))

    if "mes que vem" in text or "proximo mes" in text:
        year = today.year + (today.month // 12)
        month = (today.month % 12) + 1
        start = date(year, month, 1)
        following_year = year + (month // 12)
        following_month = (month % 12) + 1
        return DateWindow(
            start=start,
            end=date(following_year, following_month, 1) - timedelta(days=1),
            source="proximo mes",
        )

    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", text)
    if numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))
        raw_year = numeric.group(3)
        year = int(raw_year) if raw_year else today.year
        if year < 100:
            year += 2000
        try:
            target = date(year, month, day)
            if not raw_year and target < today:
                target = date(year + 1, month, day)
            return DateWindow(start=target, end=target, source=numeric.group(0))
        except ValueError:
            return None

    for phrase, weekday in sorted(WEEKDAYS.items(), key=lambda item: len(item[0]), reverse=True):
        if not re.search(rf"\b{re.escape(phrase)}\b", text):
            continue
        offset = (weekday - today.weekday()) % 7
        prefix = text[max(0, text.find(phrase) - 10) : text.find(phrase)]
        if "proxim" in prefix and offset == 0:
            offset = 7
        target = today + timedelta(days=offset)
        return DateWindow(start=target, end=target, source=phrase)

    if "fim de semana" in text:
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        return DateWindow(start=saturday, end=saturday + timedelta(days=1), source="fim de semana")
    if "esta semana" in text or "essa semana" in text:
        return DateWindow(start=today, end=today + timedelta(days=6 - today.weekday()), source="esta semana")
    return None


def period_from_message(message: str) -> Literal["morning", "afternoon", "evening"] | None:
    text = normalized_text(message)
    tokens = set(text.split())
    if "manha" in tokens:
        return "morning"
    if "tarde" in tokens:
        return "afternoon"
    if "noite" in tokens:
        return "evening"
    return None


def local_datetime(value: datetime, timezone_name: str) -> datetime:
    zone = tenant_timezone(timezone_name)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(zone)


def local_to_utc(day: date, value: time, timezone_name: str) -> datetime:
    return datetime.combine(day, value, tzinfo=tenant_timezone(timezone_name)).astimezone(timezone.utc)


def human_date(value: date) -> str:
    return f"{WEEKDAY_NAMES[value.weekday()]}, {value.day} de {MONTH_NAMES[value.month - 1]}"


def human_datetime(value: datetime, timezone_name: str) -> str:
    local = local_datetime(value, timezone_name)
    return f"{human_date(local.date())}, às {local:%H:%M}"
