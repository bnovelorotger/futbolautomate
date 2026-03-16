from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TypefullyDraftRequest(BaseModel):
    social_set_id: str
    text: str
    dry_run: bool = False


class TypefullyDraftResponse(BaseModel):
    draft_id: str
    social_set_id: str
    exported_at: datetime
    raw_response: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class TypefullySocialSet(BaseModel):
    id: str
    name: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

