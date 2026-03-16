from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import ContentType, ViralStoryType
from app.schemas.common import IngestStats


class EditorialViralStoryCandidateView(BaseModel):
    competition_slug: str
    competition_name: str
    content_type: ContentType = ContentType.VIRAL_STORY
    story_type: ViralStoryType
    priority: int
    title: str
    teams: list[str] = Field(default_factory=list)
    metric_value: float | int | None = None
    excerpt: str
    text_draft: str
    source_summary_hash: str


class EditorialViralStoriesResult(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    generated_at: datetime
    rows: list[EditorialViralStoryCandidateView] = Field(default_factory=list)


class EditorialViralStoriesGenerationResult(EditorialViralStoriesResult):
    stats: IngestStats = Field(default_factory=IngestStats)
