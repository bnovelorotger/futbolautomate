from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import ContentCandidateStatus, ContentType
from app.schemas.common import IngestStats


class ContentCandidateDraft(BaseModel):
    competition_slug: str
    content_type: ContentType
    priority: int
    text_draft: str
    formatted_text: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    source_summary_hash: str
    scheduled_at: datetime | None = None
    status: ContentCandidateStatus = ContentCandidateStatus.DRAFT


class ContentGenerationResult(BaseModel):
    competition_slug: str
    competition_name: str
    summary_hash: str
    generated_at: datetime
    candidates: list[ContentCandidateDraft] = Field(default_factory=list)
    stats: IngestStats = Field(default_factory=IngestStats)
