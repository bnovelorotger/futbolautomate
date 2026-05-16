from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class XBrowserPublishResponse(BaseModel):
    text: str
    published_at: datetime | None = None
    dry_run: bool = False
    image_path: str | None = None
