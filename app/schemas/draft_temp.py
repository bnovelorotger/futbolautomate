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
    quality_check_preview_passed: bool | None = None
    quality_check_preview_errors: list[str] = Field(default_factory=list)
    has_formatted: bool = False
    has_rewrite: bool = False
    phase3_rollout_eligible: bool = False
    phase3_rollout_reason: str | None = None
    editorial_voice_request: dict[str, Any] | None = None
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
    phase3_candidate_count: int = 0
    phase3_eligible_count: int = 0
    phase3_quality_passed_count: int = 0
    phase3_quality_failed_count: int = 0


class DraftTempSnapshot(BaseModel):
    generated_at: datetime
    source: str = "content_candidates"
    limit: int
    include_rejected: bool = False
    phase3_only: bool = False
    recompute_quality_checks: bool = False
    prefer_rewrite: bool = True
    summary: DraftTempSummary
    rows: list[DraftTempCandidateView] = Field(default_factory=list)
