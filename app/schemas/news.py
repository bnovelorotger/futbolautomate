from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import NewsType, SourceName


class NewsRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    source_name: SourceName
    source_url: str
    title: str
    subtitle: str | None = None
    published_at: datetime | None = None
    summary: str | None = None
    body_text: str | None = None
    news_type: NewsType = NewsType.OTHER
    clubs_detected: list[str] = Field(default_factory=list)
    competition_detected: str | None = None
    raw_category: str | None = None
    scraped_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)

