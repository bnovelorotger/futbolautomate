from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EditorialRewriteLLMRequest(BaseModel):
    prompt: str
    max_chars: int


class EditorialRewriteLLMResponse(BaseModel):
    rewritten_text: str
    model: str
    rewritten_at: datetime
    raw_response: dict[str, Any] = Field(default_factory=dict)

