from __future__ import annotations

from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.config import Settings
from app.core.enums import SourceName
from app.core.exceptions import FetchError, RobotsPolicyError
from app.schemas.common import FetchArtifact
from app.utils.urls import is_allowed_by_robots


class HTTPClient:
    def __init__(self, source_name: SourceName, base_url: str, settings: Settings, headers: dict[str, str]):
        self.source_name = source_name
        self.base_url = base_url
        self.settings = settings
        self.headers = {"User-Agent": settings.user_agent, **headers}
        self.session = requests.Session()
        retries = Retry(
            total=settings.request_retries,
            backoff_factor=settings.request_backoff_seconds,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get(self, url: str) -> FetchArtifact:
        if self.settings.respect_robots_txt and not is_allowed_by_robots(
            self.base_url, self.settings.user_agent, url
        ):
            raise RobotsPolicyError(f"robots.txt no permite {url}")
        response = self.session.get(
            url,
            timeout=self.settings.request_timeout_seconds,
            headers=self.headers,
        )
        if response.status_code >= 400:
            raise FetchError(f"{self.source_name} devolvio HTTP {response.status_code} para {url}")
        return FetchArtifact(
            source_name=self.source_name,
            requested_url=url,
            final_url=str(response.url),
            content=response.text,
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            fetched_at=datetime.now(timezone.utc),
        )

