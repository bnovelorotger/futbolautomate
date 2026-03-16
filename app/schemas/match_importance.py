from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import ContentType
from app.schemas.common import IngestStats


class MatchImportanceRowView(BaseModel):
    competition_slug: str
    competition_name: str
    round_name: str | None = None
    match_date: date | None = None
    source_url: str
    home_team: str
    away_team: str
    home_position: int | None = None
    away_position: int | None = None
    home_recent_points: int | None = None
    away_recent_points: int | None = None
    importance_score: int
    tags: list[str] = Field(default_factory=list)
    score_reasoning: list[str] = Field(default_factory=list)


class FeaturedMatchCandidateView(BaseModel):
    competition_slug: str
    competition_name: str
    content_type: ContentType
    priority: int
    home_team: str
    away_team: str
    importance_score: int
    tags: list[str] = Field(default_factory=list)
    excerpt: str
    text_draft: str
    source_summary_hash: str


class MatchImportanceResult(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    generated_at: datetime
    rows: list[MatchImportanceRowView] = Field(default_factory=list)


class MatchImportanceGenerationResult(MatchImportanceResult):
    stats: IngestStats = Field(default_factory=IngestStats)
    generated_candidates: list[FeaturedMatchCandidateView] = Field(default_factory=list)
