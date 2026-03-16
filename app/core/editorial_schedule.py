from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

from app.core.catalog import load_competition_catalog
from app.schemas.editorial_planner import EditorialWeeklySchedule

EDITORIAL_WEEKDAY_ORDER = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

_WEEKDAY_LABELS = {
    "monday": "lunes",
    "tuesday": "martes",
    "wednesday": "miercoles",
    "thursday": "jueves",
    "friday": "viernes",
    "saturday": "sabado",
    "sunday": "domingo",
}

_WEEKDAY_ALIASES = {
    "monday": "monday",
    "lunes": "monday",
    "tuesday": "tuesday",
    "martes": "tuesday",
    "wednesday": "wednesday",
    "miercoles": "wednesday",
    "thursday": "thursday",
    "jueves": "thursday",
    "friday": "friday",
    "viernes": "friday",
    "saturday": "saturday",
    "sabado": "saturday",
    "sunday": "sunday",
    "domingo": "sunday",
}


def _normalize_weekday_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return normalized.strip().lower()


def canonical_editorial_weekday(value: str) -> str:
    token = _normalize_weekday_token(value)
    try:
        return _WEEKDAY_ALIASES[token]
    except KeyError as exc:
        raise ValueError(f"Dia de planning no soportado: {value}") from exc


def editorial_weekday_for_date(target_date) -> str:
    return EDITORIAL_WEEKDAY_ORDER[target_date.weekday()]


def editorial_weekday_label(value: str) -> str:
    canonical = canonical_editorial_weekday(value)
    return _WEEKDAY_LABELS[canonical]


def normalize_editorial_schedule(schedule: EditorialWeeklySchedule) -> EditorialWeeklySchedule:
    competition_catalog = load_competition_catalog()
    normalized_plan = {weekday: [] for weekday in EDITORIAL_WEEKDAY_ORDER}

    for weekday, rules in schedule.weekly_plan.items():
        canonical_weekday = canonical_editorial_weekday(weekday)
        for rule in rules:
            if rule.competition_slug not in competition_catalog:
                raise ValueError(
                    f"Competicion desconocida en el planning editorial: {rule.competition_slug}"
                )
            normalized_plan[canonical_weekday].append(rule)

    return schedule.model_copy(update={"weekly_plan": normalized_plan})


@lru_cache(maxsize=4)
def load_editorial_schedule(path: Path | None = None) -> EditorialWeeklySchedule:
    schedule_path = path or Path(__file__).resolve().parents[1] / "config" / "editorial_schedule.json"
    with schedule_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return normalize_editorial_schedule(EditorialWeeklySchedule.model_validate(payload))
