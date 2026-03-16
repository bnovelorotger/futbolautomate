from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NewsEditorialRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    news_id: int
    sport_detected: str | None = None
    is_football: bool = False
    is_balearic_related: bool = False
    clubs_detected: list[str] = Field(default_factory=list)
    competition_detected: str | None = None
    editorial_relevance_score: int = 0
    signals: dict[str, Any] = Field(default_factory=dict)
    analyzed_at: datetime
