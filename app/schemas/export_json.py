from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ExportJsonEntry(BaseModel):
    id: int
    content_type: str
    competition: str
    group: str
    match_date: date | None = None
    tweet: str
    created_at: datetime


class ExportJsonBlockedSeries(BaseModel):
    content_type: str
    competition: str
    group: str
    round_label: str
    expected_parts: list[int] = Field(default_factory=list)
    available_parts: list[int] = Field(default_factory=list)
    passed_parts: list[int] = Field(default_factory=list)
    partition_series_complete: bool
    blocked_reason: str | None = None


class ExportJsonResult(BaseModel):
    dry_run: bool
    reference_date: date
    path: str
    generated_count: int
    blocked_series_count: int = 0
    blocked_series: list[ExportJsonBlockedSeries] = Field(default_factory=list)
    rows: list[ExportJsonEntry] = Field(default_factory=list)
