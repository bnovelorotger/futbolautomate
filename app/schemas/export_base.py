from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ExportBaseItem(BaseModel):
    id: int
    text: str
    selected_text_source: str
    competition_slug: str
    content_type: str
    image_path: str | None = None
    priority: int
    created_at: datetime


class ExportBaseDocument(BaseModel):
    scope: str
    target_date: date
    window_start: date
    window_end: date
    generated_at: datetime
    total_items: int
    competitions: dict[str, dict[str, list[ExportBaseItem]]] = Field(default_factory=dict)


class ExportBaseResult(BaseModel):
    scope: str
    target_date: date
    window_start: date
    window_end: date
    path: str
    total_items: int
    generated_at: datetime
    document: ExportBaseDocument
