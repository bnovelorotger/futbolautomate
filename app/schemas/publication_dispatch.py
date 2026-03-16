from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.core.enums import ContentCandidateStatus, ContentType


class PublicationCandidateView(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime
    excerpt: str


class PublicationDispatchResult(BaseModel):
    dry_run: bool
    dispatched_count: int
    rows: list[PublicationCandidateView]


class PublicationDispatchSummary(BaseModel):
    total_ready: int
    total_approved_future: int
    total_published: int
    total_rejected: int
    total_drafts: int
