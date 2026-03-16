from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import ContentCandidateStatus, ContentType


class EditorialQualityCheckCandidateView(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    text_source: str
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    quality_checked_at: datetime | None = None
    excerpt: str


class EditorialQualityCheckCandidateDetail(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    text_source: str
    selected_text: str
    payload_json: dict[str, Any] = Field(default_factory=dict)
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    quality_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EditorialQualityCheckResult(BaseModel):
    dry_run: bool
    candidate: EditorialQualityCheckCandidateDetail


class EditorialQualityCheckBatchResult(BaseModel):
    dry_run: bool
    reference_date: date | None = None
    checked_count: int
    passed_count: int
    failed_count: int
    rows: list[EditorialQualityCheckCandidateView] = Field(default_factory=list)
