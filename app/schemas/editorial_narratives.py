from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import ContentType, NarrativeMetricType
from app.schemas.common import IngestStats


class EditorialNarrativeCandidateView(BaseModel):
    competition_slug: str
    competition_name: str
    content_type: ContentType = ContentType.METRIC_NARRATIVE
    narrative_type: NarrativeMetricType
    priority: int
    team: str | None = None
    metric_value: float | int | None = None
    excerpt: str
    text_draft: str
    source_summary_hash: str


class EditorialNarrativesResult(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    generated_at: datetime
    rows: list[EditorialNarrativeCandidateView] = Field(default_factory=list)


class EditorialNarrativesGenerationResult(EditorialNarrativesResult):
    stats: IngestStats = Field(default_factory=IngestStats)
