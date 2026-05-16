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
    """Session expired or invalid - re-run browser-auth-capture."""


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

    def publish_text(
        self,
        text: str,
        *,
        image_path: Path | None = None,
        dry_run: bool = False,
    ) -> XBrowserPublishResponse:
        if not text or not text.strip():
            raise XBrowserPublishError("Tweet text cannot be empty")
        if len(text) > MAX_POST_LENGTH:
            raise XBrowserPublishError(f"Tweet text exceeds {MAX_POST_LENGTH} chars ({len(text)})")
        if dry_run:
            logger.info("[dry-run] Would publish: %s…", text[:60])
            if image_path is not None and image_path.exists():
                logger.info("[dry-run] Would attach image: %s", image_path.name)
            return XBrowserPublishResponse(text=text, dry_run=True)
        if not self.state_file.exists():
            raise XBrowserSessionError(f"No session file at {self.state_file}. Run: browser-auth-capture")

        resolved_image: Path | None = image_path if (image_path is not None and image_path.exists()) else None

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
                    raise XBrowserSessionError("Session expired. Run: browser-auth-capture")
                page.wait_for_selector(self.TEXTAREA_SELECTOR, timeout=15_000)
                if resolved_image is not None:
                    try:
                        page.set_input_files('[data-testid="fileInput"]', str(resolved_image))
                        page.wait_for_selector('[data-testid="attachments"]', timeout=20_000)
                        logger.info("Image attached: %s", resolved_image.name)
                    except Exception as exc:
                        logger.warning("Image attachment failed, continuing without image: %s", exc)
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
            image_path=str(resolved_image) if resolved_image is not None else None,
        )

    def publish_thread(
        self,
        tweets: list[tuple[str, Path | None]],
        *,
        dry_run: bool = False,
    ) -> XBrowserPublishResponse:
        if len(tweets) < 2:
            raise XBrowserPublishError("publish_thread requires at least 2 tweets; use publish_text for single tweets")
        for idx, (text, _) in enumerate(tweets):
            if not text or not text.strip():
                raise XBrowserPublishError(f"Tweet slot {idx} text cannot be empty")
            if len(text) > MAX_POST_LENGTH:
                raise XBrowserPublishError(
                    f"Tweet slot {idx} text exceeds {MAX_POST_LENGTH} chars ({len(text)})"
                )

        if dry_run:
            for idx, (text, image_path) in enumerate(tweets):
                logger.info("[dry-run] Thread slot %d: %s…", idx, text[:60])
                if image_path is not None and image_path.exists():
                    logger.info("[dry-run] Thread slot %d would attach image: %s", idx, image_path.name)
            combined = "\n---\n".join(text for text, _ in tweets)
            return XBrowserPublishResponse(text=combined, dry_run=True)

        if not self.state_file.exists():
            raise XBrowserSessionError(f"No session file at {self.state_file}. Run: browser-auth-capture")

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
                    raise XBrowserSessionError("Session expired. Run: browser-auth-capture")
                page.wait_for_selector(self.TEXTAREA_SELECTOR, timeout=15_000)

                # Slot 0
                slot_text, slot_image = tweets[0]
                if slot_image is not None and slot_image.exists():
                    try:
                        page.set_input_files('[data-testid="fileInput"]', str(slot_image))
                        page.wait_for_selector('[data-testid="attachments"]', timeout=20_000)
                        logger.info("Thread slot 0 image attached: %s", slot_image.name)
                    except Exception as exc:
                        logger.warning("Thread slot 0 image attachment failed, continuing: %s", exc)
                textarea = page.locator('[data-testid^="tweetTextarea"]').nth(0)
                textarea.scroll_into_view_if_needed(timeout=5_000)
                textarea.click(force=True, timeout=15_000)
                page.keyboard.type(slot_text, delay=self.typing_delay_ms)

                # Slots 1..N-1
                for slot_index in range(1, len(tweets)):
                    slot_text, slot_image = tweets[slot_index]
                    add_button = page.locator('[data-testid="addButton"]')
                    add_button.wait_for(state="visible", timeout=10_000)
                    add_button.click(timeout=10_000)
                    # Wait for a new textarea slot to appear
                    page.wait_for_function(
                        f"() => document.querySelectorAll('[data-testid^=\"tweetTextarea\"]').length > {slot_index}",
                        timeout=10_000,
                    )
                    if slot_image is not None and slot_image.exists():
                        try:
                            page.locator('[data-testid="fileInput"]').nth(slot_index).set_input_files(
                                str(slot_image), timeout=10_000
                            )
                            logger.info("Thread slot %d image attached: %s", slot_index, slot_image.name)
                        except Exception as exc:
                            logger.warning(
                                "Thread slot %d image attachment failed, continuing: %s", slot_index, exc
                            )
                    new_textarea = page.locator('[data-testid^="tweetTextarea"]').nth(slot_index)
                    new_textarea.scroll_into_view_if_needed(timeout=5_000)
                    new_textarea.click(force=True, timeout=10_000)
                    page.keyboard.type(slot_text, delay=self.typing_delay_ms)

                page.wait_for_function(
                    "() => {"
                    "  const btn = document.querySelector('[data-testid=\"tweetButton\"]');"
                    "  return btn && btn.getAttribute('aria-disabled') !== 'true';"
                    "}",
                    timeout=10_000,
                )
                time.sleep(2)
                page.keyboard.press("Control+Enter")
                try:
                    page.wait_for_url(
                        lambda url: "/compose/post" not in url,
                        timeout=15_000,
                    )
                except PlaywrightTimeout:
                    error_els = page.locator('[data-testid="toast"], [role="alert"]').all()
                    errors = [el.inner_text()[:200] for el in error_els if el.is_visible()]
                    detail = (
                        "; ".join(errors) if errors else "page did not navigate away from compose after 15s"
                    )
                    raise XBrowserPublishError(f"Thread submission may have failed: {detail}")
                context.storage_state(path=str(self.state_file))
            except (XBrowserSessionError, XBrowserPublishError):
                raise
            except PlaywrightTimeout as exc:
                raise XBrowserPublishError(f"Timeout during browser thread publish: {exc}") from exc
            except Exception as exc:
                raise XBrowserPublishError(f"Browser thread publish failed: {exc}") from exc
            finally:
                browser.close()

        combined = "\n---\n".join(text for text, _ in tweets)
        logger.info("Published thread via browser (%d tweets)", len(tweets))
        return XBrowserPublishResponse(
            text=combined,
            published_at=datetime.now(timezone.utc),
            dry_run=False,
        )
