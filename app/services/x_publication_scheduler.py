from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import Settings, get_settings
from app.db.models import ContentCandidate

DEFAULT_MAX_PUBLICATION_ATTEMPTS = 3

_WEEKDAY_TO_KEY = {
    0: "lunes",
    1: "martes",
    2: "miercoles",
    3: "jueves",
    4: "viernes",
    5: "sabado",
    6: "domingo",
}


@dataclass(frozen=True)
class PublicationDaySchedule:
    day_key: str
    publish_after: time
    types: frozenset[str]


@dataclass(frozen=True)
class PublicationSchedule:
    days: dict[str, PublicationDaySchedule]

    def day(self, key: str) -> PublicationDaySchedule | None:
        return self.days.get(key)


def _default_schedule_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "publication_schedule.json"


def _parse_publish_after(value: str, *, day_key: str) -> time:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(hour=int(hour_text), minute=int(minute_text))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Hora de publicacion invalida para {day_key}: {value!r}") from exc


@lru_cache(maxsize=4)
def load_publication_schedule(path: Path | None = None) -> PublicationSchedule:
    schedule_path = path or _default_schedule_path()
    with schedule_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    days: dict[str, PublicationDaySchedule] = {}
    for day_key, raw_entry in payload.items():
        publish_after = _parse_publish_after(raw_entry["publish_after"], day_key=day_key)
        types = frozenset(str(content_type).strip() for content_type in raw_entry["types"] if str(content_type).strip())
        days[day_key] = PublicationDaySchedule(
            day_key=day_key,
            publish_after=publish_after,
            types=types,
        )
    return PublicationSchedule(days=days)


class XPublicationScheduler:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        schedule: PublicationSchedule | None = None,
        schedule_path: Path | None = None,
        now_provider: Callable[[], datetime] | None = None,
        max_publication_attempts: int = DEFAULT_MAX_PUBLICATION_ATTEMPTS,
    ) -> None:
        self.settings = settings or get_settings()
        self.schedule = schedule or load_publication_schedule(schedule_path)
        self.timezone = ZoneInfo(self.settings.timezone)
        self.now_provider = now_provider or (lambda: datetime.now(self.timezone))
        self.max_publication_attempts = max_publication_attempts

    def current_local_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            return current.replace(tzinfo=self.timezone)
        return current.astimezone(self.timezone)

    def is_retry_allowed(self, candidate: ContentCandidate) -> bool:
        if candidate.external_publication_ref:
            return False
        if not candidate.external_publication_error:
            return True
        return (candidate.publication_attempts or 0) < self.max_publication_attempts

    def is_scheduled_now(self, candidate: ContentCandidate, *, now: datetime | None = None) -> bool:
        current = now or self.current_local_time()
        current = current.replace(tzinfo=self.timezone) if current.tzinfo is None else current.astimezone(self.timezone)

        day_key = _WEEKDAY_TO_KEY[current.weekday()]
        day_schedule = self.schedule.day(day_key)
        if day_schedule is None:
            return False
        if candidate.content_type not in day_schedule.types:
            return False
        return current.time().replace(second=0, microsecond=0) >= day_schedule.publish_after

    def is_candidate_publishable(self, candidate: ContentCandidate, *, now: datetime | None = None) -> bool:
        return self.is_retry_allowed(candidate) and self.is_scheduled_now(candidate, now=now)

    def filter_candidates(
        self,
        candidates: list[ContentCandidate],
        *,
        now: datetime | None = None,
    ) -> list[ContentCandidate]:
        return [candidate for candidate in candidates if self.is_candidate_publishable(candidate, now=now)]
