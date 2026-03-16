from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def madrid_now() -> datetime:
    return datetime.now(ZoneInfo("Europe/Madrid"))

