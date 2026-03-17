from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import ContentCandidateStatus, ContentType


class EditorialApprovalCandidateView(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    autoapprovable: bool
    policy_reason: str
    autoapproved: bool | None = None
    autoapproved_at: datetime | None = None
    autoapproval_reason: str | None = None
    importance_score: int | None = None
    priority_bucket: str | None = None
    importance_reasoning: list[str] = Field(default_factory=list)
    created_at: datetime
    excerpt: str


class EditorialApprovalStatusView(BaseModel):
    enabled: bool
    autoapprovable_content_types: list[ContentType] = Field(default_factory=list)
    conditional_autoapprovable_content_types: list[ContentType] = Field(default_factory=list)
    manual_review_content_types: list[ContentType] = Field(default_factory=list)
    drafts_found: int
    autoapprovable_count: int
    manual_review_count: int


class EditorialApprovalRunResult(BaseModel):
    dry_run: bool
    reference_date: date | None = None
    drafts_found: int
    autoapprovable_count: int
    autoapproved_count: int
    manual_review_count: int
    rows: list[EditorialApprovalCandidateView] = Field(default_factory=list)
