from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import ContentType
from app.schemas.common import IngestStats


class StandingsRoundupRowView(BaseModel):
    position: int
    team: str
    points: int | None = None
    played: int | None = None
    zone_tag: str | None = None


class StandingsRoundupPreviewResult(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    generated_at: datetime
    group_label: str | None = None
    selected_rows_count: int = 0
    omitted_rows_count: int = 0
    max_characters: int
    text_draft: str | None = None
    rows: list[StandingsRoundupRowView] = Field(default_factory=list)


class StandingsRoundupCandidateView(BaseModel):
    competition_slug: str
    competition_name: str
    content_type: ContentType
    priority: int
    group_label: str | None = None
    selected_rows_count: int
    omitted_rows_count: int
    excerpt: str
    text_draft: str


class StandingsRoundupGenerationResult(StandingsRoundupPreviewResult):
    stats: IngestStats = Field(default_factory=IngestStats)
    generated_candidates: list[StandingsRoundupCandidateView] = Field(default_factory=list)
