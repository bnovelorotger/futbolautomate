from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class EditorialDayPlanScheduleSummary(BaseModel):
    day_key: str
    publish_after: str | None = None
    scheduled_types: list[str] = Field(default_factory=list)


class EditorialDayPlanStatusSummary(BaseModel):
    total_candidates: int
    published_count: int
    approved_count: int
    draft_count: int
    rejected_count: int
    pending_count: int


class EditorialDayPlanTypeItem(BaseModel):
    content_type: str
    count: int


class EditorialDayPlanEntry(BaseModel):
    id: int
    status: str
    content_type: str
    competition: str
    priority: int


class EditorialDayPlanReport(BaseModel):
    target_date: date
    timezone: str
    generated_at: datetime
    schedule: EditorialDayPlanScheduleSummary
    status: EditorialDayPlanStatusSummary
    by_content_type: list[EditorialDayPlanTypeItem] = Field(default_factory=list)
    entries: list[EditorialDayPlanEntry] = Field(default_factory=list)
