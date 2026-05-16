from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import MatchEventType

TeamSide = Literal["home", "away"]


class MatchEventRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    team_side: TeamSide
    event_type: MatchEventType = MatchEventType.GOAL
    period: str | None = None
    minute_raw: str | None = None
    minute: int | None = None
    minute_extra: int | None = None
    player_raw: str | None = None
    player_source_url: str | None = None
    sort_order: int = 0
    source_event_key: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class MatchEventView(BaseModel):
    id: int
    match_id: int
    team_id: int | None = None
    team_side: TeamSide
    event_type: MatchEventType
    period: str | None = None
    minute_raw: str | None = None
    minute: int | None = None
    minute_extra: int | None = None
    player_raw: str | None = None
    player_source_url: str | None = None
    sort_order: int
    source_event_key: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class MatchEventEnrichmentMatchView(BaseModel):
    match_id: int
    source_url: str
    detail_url: str
    home_team: str
    away_team: str
    events_found: int = 0
    persisted: bool = False
    has_scorers: bool = False


class MatchEventEnrichmentResult(BaseModel):
    checked_count: int = 0
    enriched_count: int = 0
    total_events_found: int = 0
    rows: list[MatchEventEnrichmentMatchView] = Field(default_factory=list)


class TopScorerRowView(BaseModel):
    player: str
    team: str
    goals: int
    latest_goal_date: date | None = None


class TopScorerResult(BaseModel):
    competition_slug: str
    generated_at: datetime
    rows: list[TopScorerRowView] = Field(default_factory=list)
