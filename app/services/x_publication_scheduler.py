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
from app.services.editorial_phase import EditorialPhaseService

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
class PublicationSlot:
    day_key: str
    publish_after: time
    types: frozenset[str]
    publish_limit: int | None = None


@dataclass(frozen=True)
class PublicationDaySchedule:
    day_key: str
    slots: tuple[PublicationSlot, ...]

    @property
    def publish_after(self) -> time:
        return self.slots[0].publish_after

    @property
    def types(self) -> frozenset[str]:
        return frozenset(content_type for slot in self.slots for content_type in slot.types)

    def active_slot_at(self, current_time: time) -> PublicationSlot | None:
        normalized_time = current_time.replace(second=0, microsecond=0)
        active_slots = [slot for slot in self.slots if normalized_time >= slot.publish_after]
        if not active_slots:
            return None
        return active_slots[-1]

    def last_slot(self) -> PublicationSlot:
        return self.slots[-1]


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


def _parse_slot(day_key: str, raw_entry: dict) -> PublicationSlot:
    publish_after = _parse_publish_after(raw_entry["publish_after"], day_key=day_key)
    types = frozenset(str(content_type).strip() for content_type in raw_entry["types"] if str(content_type).strip())
    raw_publish_limit = raw_entry.get("publish_limit", raw_entry.get("limit"))
    publish_limit = None
    if raw_publish_limit is not None:
        publish_limit = max(int(raw_publish_limit), 1)
    return PublicationSlot(
        day_key=day_key,
        publish_after=publish_after,
        types=types,
        publish_limit=publish_limit,
    )


@lru_cache(maxsize=4)
def load_publication_schedule(path: Path | None = None) -> PublicationSchedule:
    schedule_path = path or _default_schedule_path()
    with schedule_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    days: dict[str, PublicationDaySchedule] = {}
    for day_key, raw_entry in payload.items():
        if "slots" in raw_entry:
            slots = tuple(
                sorted(
                    (_parse_slot(day_key, slot) for slot in raw_entry["slots"]),
                    key=lambda slot: slot.publish_after,
                )
            )
        else:
            slots = (_parse_slot(day_key, raw_entry),)
        if not slots:
            raise ValueError(f"Dia sin slots de publicacion: {day_key}")
        days[day_key] = PublicationDaySchedule(
            day_key=day_key,
            slots=slots,
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
        phase_service: EditorialPhaseService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.schedule = schedule or load_publication_schedule(schedule_path)
        self.timezone = ZoneInfo(self.settings.timezone)
        self.now_provider = now_provider or (lambda: datetime.now(self.timezone))
        self.max_publication_attempts = max_publication_attempts
        self.phase_service = phase_service

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
        active_slot = day_schedule.active_slot_at(current.time())
        if active_slot is None:
            return False
        if candidate.content_type not in active_slot.types:
            return False
        if self.phase_service is not None and not self.phase_service.is_candidate_allowed(
            candidate,
            reference_date=current.date(),
        ):
            return False
        return True

    def is_candidate_publishable(self, candidate: ContentCandidate, *, now: datetime | None = None) -> bool:
        return self.is_retry_allowed(candidate) and self.is_scheduled_now(candidate, now=now)

    def filter_candidates(
        self,
        candidates: list[ContentCandidate],
        *,
        now: datetime | None = None,
    ) -> list[ContentCandidate]:
        return [candidate for candidate in candidates if self.is_candidate_publishable(candidate, now=now)]
