from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.core.enums import ContentCandidateStatus, ContentType


class TypefullyExportCandidateView(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    has_rewrite: bool = False
    text_source: str = "text_draft"
    external_publication_ref: str | None = None
    external_channel: str | None = None
    external_exported_at: datetime | None = None
    external_publication_attempted_at: datetime | None = None
    external_publication_error: str | None = None
    excerpt: str


class TypefullyExportResult(BaseModel):
    dry_run: bool
    candidate: TypefullyExportCandidateView


class TypefullyBatchExportResult(BaseModel):
    dry_run: bool
    exported_count: int
    rows: list[TypefullyExportCandidateView]


class TypefullyConfigStatus(BaseModel):
    ready: bool
    has_api_key: bool
    has_api_url: bool
    api_url: str | None = None
    social_set_id: str | None = None
    social_set_strategy: str
