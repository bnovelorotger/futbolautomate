from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import SourceName


class StandingRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    source_name: SourceName
    source_url: str
    competition_code: str | None = None
    competition_name: str | None = None
    season: str | None = None
    group_name: str | None = None
    position: int
    team_name: str
    played: int | None = None
    wins: int | None = None
    draws: int | None = None
    losses: int | None = None
    goals_for: int | None = None
    goals_against: int | None = None
    goal_difference: int | None = None
    points: int | None = None
    form_text: str | None = None
    scraped_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)

