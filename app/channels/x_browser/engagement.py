from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.channels.x_browser.auth import _PROFILE_DIR, _STEALTH_ARGS, _STEALTH_JS, _USER_AGENT
from app.channels.x_browser.publisher import XBrowserSessionError

logger = logging.getLogger(__name__)

_MAX_SCROLL_RETRIES = 3
_SCROLL_PX = 600
_SCROLL_PAUSE_SECONDS = 2


@dataclass
class EngagementResult:
    liked: int
    attempted: int
    dry_run: bool


def engage_timeline(
    *,
    likes: int = 3,
    state_file: Path,
    dry_run: bool = False,
) -> EngagementResult:
    """Navigate to home timeline, like `likes` tweets from followed accounts.

    Uses persistent context (same profile as publisher). Adds human-like delays
    between actions. Skips already-liked tweets.
    """
    _PROFILE_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(_PROFILE_DIR),
            headless=True,
            args=_STEALTH_ARGS,
            user_agent=_USER_AGENT,
        )
        page = context.new_page()
        page.add_init_script(_STEALTH_JS)

        try:
            page.goto("https://x.com/home", wait_until="networkidle", timeout=30_000)

            if "/login" in page.url or "/i/flow" in page.url:
                raise XBrowserSessionError("Session expired. Run: browser-auth-capture")

            liked = 0
            attempted = 0

            for attempt in range(_MAX_SCROLL_RETRIES):
                like_buttons = page.locator('[data-testid="like"]').all()
                logger.debug("Scroll pass %d: found %d like buttons", attempt + 1, len(like_buttons))

                for btn in like_buttons:
                    if liked >= likes:
                        break

                    try:
                        if not btn.is_visible():
                            continue
                        if not btn.is_enabled():
                            continue
                        # is_in_viewport only available on locator — use bounding_box as proxy
                        box = btn.bounding_box()
                        if box is None:
                            continue
                    except Exception:
                        continue

                    attempted += 1

                    if dry_run:
                        logger.info("[dry-run] Would like tweet (button %d)", attempted)
                    else:
                        try:
                            btn.click()
                            liked += 1
                            logger.debug("Liked tweet %d/%d", liked, likes)
                        except Exception as exc:
                            logger.warning("Failed to click like button: %s", exc)
                            continue

                        time.sleep(random.uniform(3, 8))

                        # Scroll mid-way through to surface more tweets
                        if liked == likes // 2:
                            page.evaluate(f"window.scrollBy(0, {_SCROLL_PX})")
                            time.sleep(_SCROLL_PAUSE_SECONDS)

                if liked >= likes:
                    break

                # Not enough liked yet — scroll and retry
                page.evaluate(f"window.scrollBy(0, {_SCROLL_PX})")
                time.sleep(_SCROLL_PAUSE_SECONDS)

            state_file.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(state_file))

        finally:
            context.close()

    if dry_run:
        logger.info("[dry-run] Would like %d tweets (found %d candidates)", likes, attempted)
        return EngagementResult(liked=0, attempted=attempted, dry_run=True)

    logger.info("Engagement complete: liked %d/%d attempted=%d", liked, likes, attempted)
    return EngagementResult(liked=liked, attempted=attempted, dry_run=False)
