from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.editorial_approval import EditorialApprovalCandidateView
from app.schemas.export_json import ExportJsonBlockedSeries, ExportJsonEntry
from app.schemas.publication_dispatch import PublicationCandidateView
from app.schemas.x_publication import XPublicationCandidateView


class EditorialReleaseResult(BaseModel):
    dry_run: bool
    reference_date: date | None = None
    drafts_found: int
    autoapprovable_count: int
    autoapproved_count: int
    manual_review_count: int
    dispatched_count: int
    export_base_total_items: int
    export_base_path: str
    x_publish_enabled: bool = False
    x_published_count: int = 0
    legacy_export_json_count: int = 0
    legacy_export_json_path: str | None = None
    legacy_export_blocked_series_count: int = 0
    legacy_export_blocked_series: list[ExportJsonBlockedSeries] = Field(default_factory=list)
    approval_rows: list[EditorialApprovalCandidateView] = Field(default_factory=list)
    dispatched_rows: list[PublicationCandidateView] = Field(default_factory=list)
    x_publication_rows: list[XPublicationCandidateView] = Field(default_factory=list)
    legacy_export_json_rows: list[ExportJsonEntry] = Field(default_factory=list)
