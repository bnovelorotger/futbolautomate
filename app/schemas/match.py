from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import MatchStatus, SourceName


class MatchRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    source_name: SourceName
    source_url: str
    competition_code: str | None = None
    competition_name: str | None = None
    season: str | None = None
    group_name: str | None = None
    round_name: str | None = None
    external_id: str | None = None
    match_date_raw: str | None = None
    match_time_raw: str | None = None
    home_team: str
    away_team: str
    home_score: int | None = None
    away_score: int | None = None
    status_raw: str | None = None
    status: MatchStatus = MatchStatus.UNKNOWN
    venue: str | None = None
    has_lineups: bool = False
    has_scorers: bool = False
    scraped_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)

