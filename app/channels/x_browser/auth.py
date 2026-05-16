from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

DEFAULT_STATE_FILE = Path(".x_browser_state.json")


def capture_session(state_file: Path = DEFAULT_STATE_FILE) -> None:
    """Open a headed browser so the user can log in. Saves session state on completion."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.goto("https://x.com/login")
        logger.info("Browser opened. Please log in to X. The window will close automatically once you reach the home page.")
        # Wait until home page is reached (user logged in)
        page.wait_for_url("**/home", timeout=180_000)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(state_file))
        logger.info("Session saved to %s", state_file)
        browser.close()


def verify_session(state_file: Path = DEFAULT_STATE_FILE) -> bool:
    """Returns True if the saved session is still valid (reaches /home without redirect to /login)."""
    if not state_file.exists():
        return False
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(state_file))
        page = context.new_page()
        page.goto("https://x.com/home", wait_until="domcontentloaded")
        valid = "/login" not in page.url
        browser.close()
        return valid
