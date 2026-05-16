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
# slow_mo makes all Playwright actions pause briefly so React processes each event.
# Without it the Post button stays aria-disabled after typing (events not flushed).
_SLOW_MO_MS = 200


class XBrowserSessionError(RuntimeError):
    """Session expired or invalid — re-run x_browser_auth capture."""


class XBrowserPublishError(RuntimeError):
    """Failed to publish tweet via browser."""


class XBrowserPublisher:
    COMPOSE_URL = "https://x.com/compose/post"
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
                slow_mo=_SLOW_MO_MS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-infobars",
                ],
            )
            context = browser.new_context(
                storage_state=str(self.state_file),
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            try:
                page.goto(self.COMPOSE_URL, wait_until="domcontentloaded", timeout=30_000)
                if "/login" in page.url or "/i/flow/login" in page.url:
                    raise XBrowserSessionError("Session expired. Run: x_browser_auth capture")
                page.wait_for_selector(self.TEXTAREA_SELECTOR, timeout=15_000)
                textarea = page.locator(self.TEXTAREA_SELECTOR).first
                textarea.scroll_into_view_if_needed(timeout=5_000)
                textarea.click(force=True, timeout=15_000)
                page.keyboard.type(text, delay=self.typing_delay_ms)
                # Wait for React to enable the Post button (aria-disabled removed after text input)
                page.wait_for_function(
                    "() => {"
                    "  const btn = document.querySelector('[data-testid=\"tweetButton\"]');"
                    "  return btn && btn.getAttribute('aria-disabled') !== 'true';"
                    "}",
                    timeout=10_000,
                )
                # Brief pause so React fully stabilises before submission
                time.sleep(2)
                # Ctrl+Enter submits the tweet via keyboard shortcut, bypassing overlay divs
                page.keyboard.press("Control+Enter")
                # X navigates away from /compose/post on successful submission
                try:
                    page.wait_for_url(
                        lambda url: "/compose/post" not in url,
                        timeout=15_000,
                    )
                except PlaywrightTimeout:
                    error_els = page.locator('[data-testid="toast"], [role="alert"]').all()
                    errors = [el.inner_text()[:200] for el in error_els if el.is_visible()]
                    detail = "; ".join(errors) if errors else "page did not navigate away from compose after 15s"
                    raise XBrowserPublishError(f"Post submission may have failed: {detail}")
                context.storage_state(path=str(self.state_file))
            except (XBrowserSessionError, XBrowserPublishError):
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
