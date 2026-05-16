from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from app.channels.x_browser.schemas import XBrowserPublishResponse

logger = logging.getLogger(__name__)

MAX_POST_LENGTH = 280


class XBrowserSessionError(RuntimeError):
    """Session expired or invalid — re-run x_browser_auth capture."""


class XBrowserPublishError(RuntimeError):
    """Failed to publish tweet via browser."""


class XBrowserPublisher:
    # Use compose/post URL directly — more reliable than clicking through home UI
    COMPOSE_URL = "https://x.com/compose/post"
    # data-testid selectors — stable across X UI versions
    TEXTAREA_SELECTOR = '[data-testid="tweetTextarea_0"]'
    POST_BUTTON_SELECTOR = '[data-testid="tweetButton"]'

    def __init__(self, state_file: Path, *, headless: bool = True, typing_delay_ms: int = 30) -> None:
        self.state_file = state_file
        self.headless = headless
        self.typing_delay_ms = typing_delay_ms

    def publish_text(self, text: str, *, dry_run: bool = False) -> XBrowserPublishResponse:
        if not text or not text.strip():
            raise XBrowserPublishError("Tweet text cannot be empty")
        if len(text) > MAX_POST_LENGTH:
            raise XBrowserPublishError(f"Tweet text exceeds {MAX_POST_LENGTH} chars ({len(text)})")
        if dry_run:
            logger.info("[dry-run] Would publish: %s…", text[:60])
            return XBrowserPublishResponse(text=text, dry_run=True)
        if not self.state_file.exists():
            raise XBrowserSessionError(f"No session file at {self.state_file}. Run: x_browser_auth capture")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                storage_state=str(self.state_file),
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            page = context.new_page()
            try:
                page.goto(self.COMPOSE_URL, wait_until="domcontentloaded", timeout=30_000)
                # Detect login redirect (session expired)
                if "/login" in page.url or "/i/flow/login" in page.url:
                    raise XBrowserSessionError("Session expired. Run: x_browser_auth capture")
                page.wait_for_selector(self.TEXTAREA_SELECTOR, timeout=15_000)
                textarea = page.locator(self.TEXTAREA_SELECTOR).first
                textarea.click()
                textarea.type(text, delay=self.typing_delay_ms)
                # Small pause before posting (human-like)
                time.sleep(0.8)
                post_btn = page.locator(self.POST_BUTTON_SELECTOR)
                post_btn.wait_for(state="visible", timeout=10_000)
                post_btn.click()
                # Wait briefly for submission to complete
                time.sleep(2)
                # Refresh session state
                context.storage_state(path=str(self.state_file))
            except XBrowserSessionError:
                raise
            except PlaywrightTimeout as exc:
                raise XBrowserPublishError(f"Timeout during browser publish: {exc}") from exc
            except Exception as exc:
                raise XBrowserPublishError(f"Browser publish failed: {exc}") from exc
            finally:
                browser.close()

        logger.info("Published via browser: %s…", text[:60])
        return XBrowserPublishResponse(
            text=text,
            published_at=datetime.now(timezone.utc),
            dry_run=False,
        )
