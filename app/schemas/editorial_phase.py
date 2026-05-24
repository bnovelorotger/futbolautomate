from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.core.enums import EditorialSeasonPhase


class EditorialCompetitionPhaseState(BaseModel):
    competition_slug: str
    reference_date: date
    phase: EditorialSeasonPhase
    reason: str
    competition_type: str | None = None
    playoff_type: str | None = None
    parent_competition: str | None = None
    child_playoff_slugs: list[str] = Field(default_factory=list)
    child_phase: EditorialSeasonPhase | None = None
    first_match_date: date | None = None
    last_match_date: date | None = None
    latest_finished_date: date | None = None
    next_scheduled_date: date | None = None
    future_scheduled_count: int = 0
    overdue_scheduled_count: int = 0
    finished_count: int = 0
    has_data: bool = False


class EditorialGlobalPhaseReport(BaseModel):
    reference_date: date
    phase: EditorialSeasonPhase
    reason: str
    states: list[EditorialCompetitionPhaseState] = Field(default_factory=list)
