from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class XPublishRequest(BaseModel):
    text: str
    dry_run: bool = False


class XPublishResponse(BaseModel):
    post_id: str
    text: str
    published_at: datetime
    raw_response: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
