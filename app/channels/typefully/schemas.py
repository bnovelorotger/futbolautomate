from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TypefullyDraftRequest(BaseModel):
    content: str
    schedule_date: datetime | None = Field(None, serialization_alias="schedule-date")
    threadify: bool = False
    auto_retweet_enabled: bool = Field(False, serialization_alias="auto-retweet-enabled")

    model_config = {"populate_by_name": True}


class TypefullyPublishResponse(BaseModel):
    draft_id: str
    draft_url: str | None = None
    scheduled_date: datetime | None = None
    text: str
    dry_run: bool = False
