from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import ContentCandidateStatus, ContentType


class EditorialQueueCandidateView(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    scheduled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None = None
    excerpt: str


class EditorialQueueCandidateDetail(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    text_draft: str
    payload_json: dict[str, Any] = Field(default_factory=dict)
    source_summary_hash: str
    scheduled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    rejection_reason: str | None = None


class EditorialQueueSummary(BaseModel):
    total_drafts: int
    total_approved: int
    total_rejected: int
    total_published: int
    total_scheduled_pending: int
