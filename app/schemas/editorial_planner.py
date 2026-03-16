from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.core.enums import ContentType, EditorialPlanningContent
from app.schemas.common import IngestStats


class EditorialScheduleRule(BaseModel):
    competition_slug: str
    content_type: EditorialPlanningContent
    priority: int = Field(default=50, ge=0, le=100)


class EditorialWeeklySchedule(BaseModel):
    timezone: str | None = None
    weekly_plan: dict[str, list[EditorialScheduleRule]] = Field(default_factory=dict)

    def rules_for_weekday(self, weekday_key: str) -> list[EditorialScheduleRule]:
        return list(self.weekly_plan.get(weekday_key, []))


class EditorialCampaignTask(BaseModel):
    date: date
    weekday_key: str
    weekday_label: str
    competition_slug: str
    competition_name: str
    planning_type: EditorialPlanningContent
    target_content_type: ContentType
    priority: int


class EditorialCampaignPlan(BaseModel):
    date: date
    weekday_key: str
    weekday_label: str
    total_tasks: int
    tasks: list[EditorialCampaignTask] = Field(default_factory=list)


class EditorialWeekPlan(BaseModel):
    reference_date: date
    week_start: date
    week_end: date
    days: list[EditorialCampaignPlan] = Field(default_factory=list)


class EditorialGeneratedTaskResult(BaseModel):
    task: EditorialCampaignTask
    generated_count: int
    stats: IngestStats = Field(default_factory=IngestStats)
    excerpts: list[str] = Field(default_factory=list)


class EditorialCampaignGenerationResult(BaseModel):
    date: date
    weekday_key: str
    weekday_label: str
    total_tasks: int
    total_generated: int
    total_inserted: int
    total_updated: int
    rows: list[EditorialGeneratedTaskResult] = Field(default_factory=list)
