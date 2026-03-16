from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import RunStatus, SourceName, TargetType


class FetchArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_name: SourceName
    requested_url: str
    final_url: str
    content: str
    status_code: int
    content_type: str | None = None
    fetched_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScrapeContext(BaseModel):
    source: SourceName
    target: TargetType
    competition_code: str | None = None
    dry_run: bool = False
    override_url: str | None = None


class IngestStats(BaseModel):
    found: int = 0
    inserted: int = 0
    updated: int = 0
    errors: int = 0


class ScrapeResult(BaseModel):
    scraper_name: str
    source_name: SourceName
    target: TargetType
    competition_code: str | None = None
    records: list[BaseModel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stats: IngestStats = Field(default_factory=IngestStats)
    status: RunStatus = RunStatus.SUCCESS

