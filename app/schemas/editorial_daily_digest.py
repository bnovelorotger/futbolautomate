from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class EditorialDailyDigestReasonItem(BaseModel):
    code: str
    count: int


class EditorialDailyDigestAlertItem(BaseModel):
    level: str
    code: str
    message: str


class EditorialDailyDigestPublicationSummary(BaseModel):
    published_to_x: int
    pending_dispatch: int
    publication_errors: int
    skipped_stale: int


class EditorialDailyDigestQueueSummary(BaseModel):
    draft_count: int
    rejected_count: int
    top_rejection_reasons: list[EditorialDailyDigestReasonItem] = Field(default_factory=list)
    top_quality_errors: list[EditorialDailyDigestReasonItem] = Field(default_factory=list)


class EditorialDailyDigestRewriteSummary(BaseModel):
    total_rewrites: int
    real_count: int
    fallback_count: int
    failed_count: int
    other_count: int
    real_ratio: float
    fallback_ratio: float
    failed_ratio: float
    other_ratio: float
    by_content_type: dict[str, dict[str, int]] = Field(default_factory=dict)


class EditorialDailyDigestReport(BaseModel):
    reference_date: date
    start_date: date
    window_days: int
    timezone: str
    generated_at: datetime
    publication: EditorialDailyDigestPublicationSummary
    queue: EditorialDailyDigestQueueSummary
    rewrite: EditorialDailyDigestRewriteSummary
    alerts: list[EditorialDailyDigestAlertItem] = Field(default_factory=list)

    @property
    def has_alerts(self) -> bool:
        return bool(self.alerts)
