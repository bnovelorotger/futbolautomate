from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.editorial_approval import EditorialApprovalCandidateView
from app.schemas.export_json import ExportJsonBlockedSeries, ExportJsonEntry
from app.schemas.publication_dispatch import PublicationCandidateView


class EditorialReleaseResult(BaseModel):
    dry_run: bool
    reference_date: date | None = None
    drafts_found: int
    autoapprovable_count: int
    autoapproved_count: int
    manual_review_count: int
    dispatched_count: int
    export_json_count: int
    export_json_path: str
    export_blocked_series_count: int = 0
    export_blocked_series: list[ExportJsonBlockedSeries] = Field(default_factory=list)
    approval_rows: list[EditorialApprovalCandidateView] = Field(default_factory=list)
    dispatched_rows: list[PublicationCandidateView] = Field(default_factory=list)
    export_json_rows: list[ExportJsonEntry] = Field(default_factory=list)
