from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class XAuthorizationStart(BaseModel):
    authorization_url: str
    state: str
    expires_at: datetime
    scopes: list[str]


class XAuthTokenStatus(BaseModel):
    ready: bool
    provider: str
    subject_id: str | None = None
    subject_username: str | None = None
    expires_at: datetime | None = None
    has_refresh_token: bool = False
    scope: str | None = None
    last_verified_at: datetime | None = None
