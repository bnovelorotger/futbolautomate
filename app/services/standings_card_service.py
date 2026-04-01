from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path

from app.core.config import get_settings
from app.db.models import ContentCandidate
from app.services.image_renderer import html_to_png, render_standings_html
from app.services.standings_image_mapper import build_standings_image_context

logger = logging.getLogger(__name__)


def generate_standings_card(
    candidate: ContentCandidate,
    output_root: Path | None = None,
    width: int = 1200,
    height: int | None = None,
    max_rows: int | None = None,
) -> str | None:
    try:
        export_root = output_root or (get_settings().app_root / "exports")
        context = build_standings_image_context(candidate, max_rows=max_rows)
        layout = dict(context.get("layout") or {})
        resolved_height = height or int(layout.get("height") or 1500)
        context["layout"] = {
            **layout,
            "width": width,
            "height": resolved_height,
            "max_rows": int(layout.get("max_rows") or len(context.get("rows") or [])),
        }

        competition_slug = _safe_path_segment(context.get("competition_slug") or candidate.competition_slug)
        date_segment = _date_segment(str(context.get("updated_at") or ""), candidate)
        filename = f"standings_roundup_{candidate.id}.png"
        html_filename = f"standings_roundup_{candidate.id}.html"

        png_relative = Path("images") / competition_slug / date_segment / filename
        html_relative = Path("tmp") / "images" / competition_slug / date_segment / html_filename

        html_path = export_root / html_relative
        png_path = export_root / png_relative

        render_standings_html(context, html_path)
        html_to_png(html_path, png_path, width=width, height=resolved_height)

        return (Path("exports") / png_relative).as_posix()
    except Exception:
        logger.exception("standings_card_generation_failed candidate_id=%s", getattr(candidate, "id", None))
        return None


def _date_segment(value: str, candidate: ContentCandidate) -> str:
    parsed = _parse_date(value)
    if parsed is not None:
        return parsed.isoformat()
    fallback = candidate.published_at or candidate.created_at or candidate.updated_at
    if fallback is not None:
        return fallback.date().isoformat()
    return datetime.now().date().isoformat()


def _parse_date(value: str) -> date | None:
    normalized = value.strip()
    if not normalized:
        return None
    for parser in (date.fromisoformat, lambda item: datetime.fromisoformat(item).date()):
        try:
            return parser(normalized)
        except ValueError:
            continue
    return None


def _safe_path_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    normalized = normalized.strip("-._")
    return normalized or "standings"
