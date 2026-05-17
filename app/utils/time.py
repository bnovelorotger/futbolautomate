from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC)


def madrid_now() -> datetime:
    return datetime.now(ZoneInfo("Europe/Madrid"))
