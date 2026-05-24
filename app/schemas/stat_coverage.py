from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.core.enums import DataCoverageStatus, DataCoverageType


class StatCoverageSummary(BaseModel):
    competition_slug: str
    data_type: DataCoverageType
    status: DataCoverageStatus
    season: str | None = None
    reference_date: date | None = None
    expected_count: int = 0
    observed_count: int = 0
    coverage_ratio: float = 0.0
    checked_at: datetime | None = None
    details: dict = {}

    @property
    def is_covered(self) -> bool:
        return self.status == DataCoverageStatus.COVERED


class StatCoverageReport(BaseModel):
    competition_slug: str
    season: str | None = None
    reference_date: date | None = None
    rows: list[StatCoverageSummary]
