from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.core.enums import RunStatus, SourceName, TargetType


class ScraperRunPayload(BaseModel):
    scraper_name: str
    source_name: SourceName
    target_type: TargetType
    competition_code: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    records_found: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    errors_count: int = 0
    error_message: str | None = None

