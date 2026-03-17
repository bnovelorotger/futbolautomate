from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, Field

from app.core.enums import ContentType
from app.schemas.common import IngestStats


class ResultsRoundupMatchView(BaseModel):
    round_name: str | None = None
    match_date: date | None = None
    match_time: time | None = None
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    source_url: str


class ResultsRoundupPreviewResult(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    generated_at: datetime
    group_label: str | None = None
    selected_matches_count: int = 0
    omitted_matches_count: int = 0
    max_characters: int
    text_draft: str | None = None
    matches: list[ResultsRoundupMatchView] = Field(default_factory=list)


class ResultsRoundupCandidateView(BaseModel):
    competition_slug: str
    competition_name: str
    content_type: ContentType
    priority: int
    group_label: str
    selected_matches_count: int
    omitted_matches_count: int
    excerpt: str
    text_draft: str


class ResultsRoundupGenerationResult(ResultsRoundupPreviewResult):
    stats: IngestStats = Field(default_factory=IngestStats)
    generated_candidates: list[ResultsRoundupCandidateView] = Field(default_factory=list)
