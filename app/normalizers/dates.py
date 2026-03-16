from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

from app.normalizers.text import normalize_spaces, strip_accents


SPANISH_MONTHS = {
    "enero": "january",
    "febrero": "february",
    "marzo": "march",
    "abril": "april",
    "mayo": "may",
    "junio": "june",
    "julio": "july",
    "agosto": "august",
    "septiembre": "september",
    "setiembre": "september",
    "octubre": "october",
    "noviembre": "november",
    "diciembre": "december",
}

SPANISH_WEEKDAYS = (
    "lunes",
    "martes",
    "miercoles",
    "jueves",
    "viernes",
    "sabado",
    "domingo",
)


@dataclass(slots=True)
class DateNormalizationResult:
    raw_date: str | None
    raw_time: str | None
    match_date: date | None
    match_time: time | None
    kickoff_datetime: datetime | None


def _normalize_date_text(raw_date: str) -> str:
    cleaned = strip_accents(raw_date).lower()
    cleaned = cleaned.replace(",", " ")
    cleaned = normalize_spaces(cleaned)
    for weekday in SPANISH_WEEKDAYS:
        cleaned = cleaned.replace(weekday, " ")
    cleaned = cleaned.replace(" de ", " ")
    for source, target in SPANISH_MONTHS.items():
        cleaned = cleaned.replace(source, target)
    return normalize_spaces(cleaned)


def parse_match_datetime(
    raw_date: str | None,
    raw_time: str | None,
    timezone_name: str = "Europe/Madrid",
) -> DateNormalizationResult:
    tzinfo = ZoneInfo(timezone_name)
    parsed_date: date | None = None
    parsed_time: time | None = None
    kickoff: datetime | None = None

    if raw_date:
        candidate = _normalize_date_text(raw_date)
        parsed_date = date_parser.parse(candidate, dayfirst=True, fuzzy=True).date()

    if raw_time:
        parsed_time = date_parser.parse(raw_time, fuzzy=True).time().replace(second=0, microsecond=0)

    if parsed_date and parsed_time:
        kickoff = datetime.combine(parsed_date, parsed_time, tzinfo=tzinfo)
    elif parsed_date:
        kickoff = datetime.combine(parsed_date, time.min, tzinfo=tzinfo)

    return DateNormalizationResult(
        raw_date=raw_date,
        raw_time=raw_time,
        match_date=parsed_date,
        match_time=parsed_time,
        kickoff_datetime=kickoff,
    )
