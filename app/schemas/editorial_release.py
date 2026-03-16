from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.editorial_approval import EditorialApprovalCandidateView
from app.schemas.publication_dispatch import PublicationCandidateView
from app.schemas.typefully_autoexport import TypefullyAutoexportCandidateView


class EditorialReleaseResult(BaseModel):
    dry_run: bool
    reference_date: date | None = None
    drafts_found: int
    autoapprovable_count: int
    autoapproved_count: int
    manual_review_count: int
    dispatched_count: int
    autoexport_scanned_count: int
    autoexport_eligible_count: int
    autoexport_exported_count: int
    autoexport_blocked_count: int
    autoexport_failed_count: int
    approval_rows: list[EditorialApprovalCandidateView] = Field(default_factory=list)
    dispatched_rows: list[PublicationCandidateView] = Field(default_factory=list)
    autoexport_rows: list[TypefullyAutoexportCandidateView] = Field(default_factory=list)
