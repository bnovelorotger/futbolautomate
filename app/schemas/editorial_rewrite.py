from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import ContentCandidateStatus, ContentType


class EditorialRewriteCandidateView(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    rewrite_status: str | None = None
    rewrite_model: str | None = None
    rewrite_timestamp: datetime | None = None
    rewrite_error: str | None = None
    excerpt: str
    rewritten_excerpt: str | None = None


class EditorialRewriteCandidateDetail(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    text_draft: str
    rewritten_text: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    rewrite_status: str | None = None
    rewrite_model: str | None = None
    rewrite_timestamp: datetime | None = None
    rewrite_error: str | None = None
    created_at: datetime
    updated_at: datetime


class EditorialRewriteResult(BaseModel):
    dry_run: bool
    overwritten: bool
    candidate: EditorialRewriteCandidateDetail


class EditorialRewriteBatchResult(BaseModel):
    dry_run: bool
    rewritten_count: int
    rows: list[EditorialRewriteCandidateView]
