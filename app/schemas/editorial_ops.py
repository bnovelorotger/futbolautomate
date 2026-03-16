from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.core.enums import ContentType, EditorialPlanningContent


class EditorialOpsTaskPreview(BaseModel):
    competition_slug: str
    competition_name: str
    planning_type: EditorialPlanningContent
    target_content_type: ContentType
    priority: int
    expected_count: int
    missing_dependencies: list[str] = Field(default_factory=list)
    excerpts: list[str] = Field(default_factory=list)


class EditorialOpsPreviewResult(BaseModel):
    date: date
    total_tasks: int
    ready_tasks: int
    blocked_tasks: int
    expected_total: int
    rows: list[EditorialOpsTaskPreview] = Field(default_factory=list)


class EditorialOpsTaskRunResult(BaseModel):
    competition_slug: str
    competition_name: str
    planning_type: EditorialPlanningContent
    target_content_type: ContentType
    priority: int
    generated_count: int
    inserted: int
    updated: int
    missing_dependencies: list[str] = Field(default_factory=list)
    excerpts: list[str] = Field(default_factory=list)


class EditorialOpsRunResult(BaseModel):
    date: date
    total_tasks: int
    generated_total: int
    inserted_total: int
    updated_total: int
    blocked_tasks: int
    rows: list[EditorialOpsTaskRunResult] = Field(default_factory=list)
