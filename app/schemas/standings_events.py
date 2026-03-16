from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import ContentType, StandingsEventType
from app.schemas.common import IngestStats


class StandingsEventView(BaseModel):
    competition_slug: str
    competition_name: str
    event_type: StandingsEventType
    team: str
    previous_position: int | None = None
    current_position: int | None = None
    position_delta: int | None = None
    priority: int
    title: str
    text_draft: str
    source_summary_hash: str


class StandingsEventsResult(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    generated_at: datetime
    current_snapshot_timestamp: datetime | None = None
    previous_snapshot_timestamp: datetime | None = None
    playoff_positions: list[int] = Field(default_factory=list)
    relegation_positions: list[int] = Field(default_factory=list)
    rows: list[StandingsEventView] = Field(default_factory=list)


class StandingsEventsGenerationResult(StandingsEventsResult):
    stats: IngestStats = Field(default_factory=IngestStats)


class StandingsEventCandidatePayload(BaseModel):
    competition_slug: str
    content_type: ContentType = ContentType.STANDINGS_EVENT
    event_type: StandingsEventType
    title: str
    team: str
    previous_position: int | None = None
    current_position: int | None = None
    position_delta: int | None = None
