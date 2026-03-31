from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

_TEMPLATES_PATH = Path(__file__).resolve().parents[1] / "templates"
_STANDINGS_TEMPLATE = "standings_card.html"


@lru_cache(maxsize=1)
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_PATH)),
        autoescape=select_autoescape(enabled_extensions=("html", "xml"), default_for_string=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_standings_html(context: dict[str, Any], output_html_path: Path) -> Path:
    template = _environment().get_template(_STANDINGS_TEMPLATE)
    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    output_html_path.write_text(template.render(**context), encoding="utf-8")
    return output_html_path


def html_to_png(html_path: Path, png_path: Path, width: int = 1200, height: int = 1500) -> Path:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        try:
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.wait_for_timeout(150)
            page.screenshot(path=str(png_path))
        finally:
            page.close()
            browser.close()
    return png_path
