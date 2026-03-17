from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import ContentCandidateStatus, ContentType


class DraftTempCandidateView(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    source_summary_hash: str
    scheduled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    external_publication_ref: str | None = None
    external_channel: str | None = None
    external_exported_at: datetime | None = None
    external_publication_error: str | None = None
    quality_check_passed: bool | None = None
    quality_check_errors: list[str] = Field(default_factory=list)
    has_formatted: bool = False
    has_rewrite: bool = False
    selected_text_source: str
    selected_text: str
    excerpt: str
    text_draft: str
    formatted_text: str | None = None
    rewritten_text: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)


class DraftTempSummary(BaseModel):
    total_candidates: int
    active_candidates: int
    included_rows: int
    draft_count: int
    approved_count: int
    rejected_count: int
    published_count: int
    scheduled_pending_count: int
    pending_export_count: int
    exported_count: int
    failed_export_count: int
    capacity_deferred_count: int


class DraftTempSnapshot(BaseModel):
    generated_at: datetime
    source: str = "content_candidates"
    limit: int
    include_rejected: bool = False
    summary: DraftTempSummary
    rows: list[DraftTempCandidateView] = Field(default_factory=list)
