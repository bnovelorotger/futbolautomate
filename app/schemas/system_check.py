from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import CompetitionIntegrationStatus, EditorialPlanningContent


class EditorialCompetitionReadinessRow(BaseModel):
    code: str
    name: str
    catalog_status: CompetitionIntegrationStatus
    seeded_in_db: bool
    planner_weekly_types: list[EditorialPlanningContent] = Field(default_factory=list)
    matches_count: int = 0
    finished_matches_count: int = 0
    scheduled_matches_count: int = 0
    standings_count: int = 0
    content_candidates_count: int = 0
    pending_export_count: int = 0
    planner_ready: bool = False
    missing_dependencies: list[str] = Field(default_factory=list)


class EditorialReadinessReport(BaseModel):
    checked_at: datetime
    integrated_catalog_count: int
    seeded_integrated_count: int
    planner_ready_count: int
    export_base_ready: bool
    export_base_path: str
    content_candidates_total: int
    content_candidates_pending_export: int
    rows: list[EditorialCompetitionReadinessRow] = Field(default_factory=list)
