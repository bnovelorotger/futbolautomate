from __future__ import annotations

from app.core.enums import MatchStatus
from app.normalizers.text import normalize_token


STATUS_MAP = {
    "programado": MatchStatus.SCHEDULED,
    "scheduled": MatchStatus.SCHEDULED,
    "aplazado": MatchStatus.POSTPONED,
    "postponed": MatchStatus.POSTPONED,
    "suspendido": MatchStatus.SUSPENDED,
    "suspended": MatchStatus.SUSPENDED,
    "cancelado": MatchStatus.CANCELLED,
    "cancelled": MatchStatus.CANCELLED,
    "abandonado": MatchStatus.ABANDONED,
    "abandoned": MatchStatus.ABANDONED,
    "finalizado": MatchStatus.FINISHED,
    "finished": MatchStatus.FINISHED,
    "full time": MatchStatus.FINISHED,
    "en juego": MatchStatus.LIVE,
    "live": MatchStatus.LIVE,
}


def normalize_match_status(raw_status: str | None) -> MatchStatus:
    if not raw_status:
        return MatchStatus.UNKNOWN
    token = normalize_token(raw_status)
    return STATUS_MAP.get(token, MatchStatus.UNKNOWN)

