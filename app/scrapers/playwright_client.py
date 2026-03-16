from __future__ import annotations

from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

from app.core.config import Settings
from app.core.enums import SourceName
from app.schemas.common import FetchArtifact


class PlaywrightClient:
    def __init__(self, source_name: SourceName, settings: Settings):
        self.source_name = source_name
        self.settings = settings

    def get(self, url: str) -> FetchArtifact:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=self.settings.user_agent)
            page.goto(url, wait_until="networkidle", timeout=self.settings.request_timeout_seconds * 1000)
            html = page.content()
            final_url = page.url
            browser.close()

        return FetchArtifact(
            source_name=self.source_name,
            requested_url=url,
            final_url=final_url,
            content=html,
            status_code=200,
            content_type="text/html",
            fetched_at=datetime.now(timezone.utc),
        )
