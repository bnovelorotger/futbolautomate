from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

DEFAULT_STATE_FILE = Path(".x_browser_state.json")
_PROFILE_DIR = Path(".x_browser_profile")

_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
]
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_STEALTH_JS = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"


def capture_session(state_file: Path = DEFAULT_STATE_FILE) -> None:
    """Open a headed browser so the user can log in. Saves session state on completion."""
    print(">>> Abriendo Chromium — haz login en X. La ventana se cerrará sola al llegar a la home.")
    _PROFILE_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        # Persistent context keeps cookies/localStorage between runs like a real browser
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(_PROFILE_DIR),
            headless=False,
            slow_mo=50,
            args=_STEALTH_ARGS,
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.add_init_script(_STEALTH_JS)
        page.goto("https://x.com/login")
        print(">>> Introduce tus credenciales de X en la ventana que se ha abierto.")
        # Wait until off the login/flow pages — up to 3 minutes
        page.wait_for_function(
            "() => !location.href.includes('/login') && !location.href.includes('/i/flow')",
            timeout=180_000,
        )
        state_file.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(state_file))
        print(f">>> Sesion guardada en {state_file}")
        context.close()


def verify_session(state_file: Path = DEFAULT_STATE_FILE) -> bool:
    """Returns True if the saved session is still valid (reaches /home without redirect to /login)."""
    if not state_file.exists():
        return False
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=_STEALTH_ARGS,
        )
        context = browser.new_context(
            storage_state=str(state_file),
            user_agent=_USER_AGENT,
        )
        page = context.new_page()
        page.add_init_script(_STEALTH_JS)
        page.goto("https://x.com/home", wait_until="domcontentloaded")
        valid = "/login" not in page.url and "/i/flow" not in page.url
        browser.close()
        return valid
