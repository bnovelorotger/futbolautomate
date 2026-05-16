"""Open the X compose page in visible mode and type a test post to diagnose browser issues."""
from __future__ import annotations

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_FILE = Path(".x_browser_state.json")
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
TEST_TEXT = "🔍 Test de automatización futbolbalear — si ves este tweet el sistema funciona (puedes ignorarlo)"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        slow_mo=300,
        args=STEALTH_ARGS,
    )
    context = browser.new_context(
        storage_state=str(STATE_FILE),
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 900},
    )
    page = context.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    print(">>> Navegando a x.com/compose/post ...")
    page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30_000)
    print(f">>> URL actual: {page.url}")

    if "/login" in page.url:
        print("❌ Sesión expirada — necesitas hacer login de nuevo con browser-auth-capture")
        browser.close()
        raise SystemExit(1)

    print(">>> Esperando textarea...")
    page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=15_000)
    textarea = page.locator('[data-testid="tweetTextarea_0"]').first
    print(f">>> Textarea visible: {textarea.is_visible()}")

    textarea.scroll_into_view_if_needed()
    textarea.click(force=True)
    print(">>> Escribiendo texto...")
    page.keyboard.type(TEST_TEXT, delay=30)

    time.sleep(1)
    post_btn = page.locator('[data-testid="tweetButton"]')
    print(f">>> Botón Post visible: {post_btn.is_visible()}, enabled: {post_btn.is_enabled()}")

    print(">>> Esperando 5 segundos para que puedas ver la pantalla antes de publicar...")
    time.sleep(5)

    print(">>> Haciendo clic en Post...")
    post_btn.click(force=True)

    print(">>> Esperando respuesta de X (10 segundos)...")
    time.sleep(10)

    print(f">>> URL después de publicar: {page.url}")
    print(">>> Revisando si hubo error...")
    error_els = page.locator('[data-testid="toast"], [role="alert"], [aria-label*="error" i]').all()
    for el in error_els:
        print(f"    MENSAJE: {el.inner_text()[:200]}")

    input(">>> Revisa la pantalla. Pulsa Enter para cerrar...")
    browser.close()
