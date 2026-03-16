from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.core.enums import ContentCandidateStatus, ContentType


class XPublicationCandidateView(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    scheduled_at: datetime | None = None
    external_publication_ref: str | None = None
    external_publication_timestamp: datetime | None = None
    external_publication_attempted_at: datetime | None = None
    external_publication_error: str | None = None
    excerpt: str


class XPublicationResult(BaseModel):
    dry_run: bool
    candidate: XPublicationCandidateView


class XBatchPublicationResult(BaseModel):
    dry_run: bool
    published_count: int
    rows: list[XPublicationCandidateView]
