from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.models import ContentCandidate

_DEFAULT_WIDTH = 1200
_DEFAULT_HEIGHT = 1500


def build_standings_image_context(candidate: ContentCandidate, max_rows: int = 10) -> dict[str, Any]:
    payload_json = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
    source_payload = payload_json.get("source_payload") if isinstance(payload_json.get("source_payload"), dict) else {}
    raw_rows = source_payload.get("rows")

    rows = [
        mapped_row
        for raw_row in (raw_rows if isinstance(raw_rows, list) else [])
        for mapped_row in [_map_row(raw_row)]
        if mapped_row is not None
    ]
    rows = sorted(rows, key=lambda row: row["position"])[: max(0, int(max_rows))]

    round_label = _string(source_payload.get("round_name")) or _string(source_payload.get("group_label"))
    group_label = _string(source_payload.get("group_label")) or _string(payload_json.get("group_label"))
    if group_label == round_label:
        group_label = None

    season_label = (
        _string(payload_json.get("season_label"))
        or _string(payload_json.get("season"))
        or _string(source_payload.get("season_label"))
        or _string(source_payload.get("season"))
    )
    updated_at = (
        _string(payload_json.get("reference_date"))
        or _string(source_payload.get("reference_date"))
        or _candidate_date(candidate)
    )

    return {
        "title": "CLASIFICACI\u00d3N",
        "competition_name": _string(payload_json.get("competition_name")) or _humanize_slug(candidate.competition_slug),
        "competition_slug": candidate.competition_slug,
        "round_label": round_label,
        "updated_at": updated_at,
        "season_label": season_label,
        "group_label": group_label,
        "rows": rows,
        "legend": {
            "playoff": {"short": "PO", "label": "Playoff"},
            "relegation": {"short": "DESC", "label": "Descenso"},
        },
        "layout": {
            "width": _DEFAULT_WIDTH,
            "height": _DEFAULT_HEIGHT,
            "max_rows": max(0, int(max_rows)),
        },
        "columns": {
            "won": any(row["won"] is not None for row in rows),
            "drawn": any(row["drawn"] is not None for row in rows),
            "lost": any(row["lost"] is not None for row in rows),
            "goal_diff": any(row["goal_diff"] is not None for row in rows),
        },
    }


def _map_row(raw_row: Any) -> dict[str, Any] | None:
    if not isinstance(raw_row, dict):
        return None

    position = _int(raw_row.get("position"))
    team_name = _string(raw_row.get("team_name")) or _string(raw_row.get("team"))
    if position is None or team_name is None:
        return None

    zone = _normalize_zone(raw_row.get("zone")) or _normalize_zone(raw_row.get("zone_tag"))
    return {
        "position": position,
        "team_name": team_name,
        "points": _int(raw_row.get("points")),
        "played": _int(raw_row.get("played")),
        "won": _int(raw_row.get("won"), raw_row.get("wins")),
        "drawn": _int(raw_row.get("drawn"), raw_row.get("draws")),
        "lost": _int(raw_row.get("lost"), raw_row.get("losses")),
        "goal_diff": _int(raw_row.get("goal_diff"), raw_row.get("goal_difference")),
        "zone": zone,
    }


def _int(*values: Any) -> int | None:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_zone(value: Any) -> str | None:
    normalized = _string(value)
    if normalized is None:
        return None
    normalized = normalized.lower()
    if normalized in {"playoff", "relegation"}:
        return normalized
    return None


def _candidate_date(candidate: ContentCandidate) -> str:
    timestamp = candidate.published_at or candidate.created_at or candidate.updated_at
    if timestamp is None:
        return datetime.now().date().isoformat()
    return timestamp.date().isoformat()


def _humanize_slug(slug: str) -> str:
    parts = [part for part in slug.replace("-", "_").split("_") if part]
    if not parts:
        return slug
    return " ".join(part.upper() if len(part) <= 3 else part.capitalize() for part in parts)
