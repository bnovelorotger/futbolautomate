from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.catalog import load_competition_catalog
from app.db.models import ContentCandidate


def build_playoff_bracket_image_context(candidate: ContentCandidate) -> dict[str, Any]:
    payload_json = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
    source_payload = payload_json.get("source_payload") if isinstance(payload_json.get("source_payload"), dict) else {}
    rounds = [row for row in source_payload.get("bracket_rounds") or [] if isinstance(row, dict)]
    visible_rounds = [_round_context(row) for row in rounds if row.get("matches")]
    total_matches = int(source_payload.get("total_matches_count") or _count_matches(visible_rounds))
    finished_matches = int(source_payload.get("finished_matches_count") or 0)
    pending_matches = int(source_payload.get("pending_matches_count") or max(total_matches - finished_matches, 0))
    row_count = sum(len(row["matches"]) for row in visible_rounds)
    height = max(1200, 300 + row_count * 104 + len(visible_rounds) * 76)
    return {
        "title": "BRACKET PLAYOFF",
        "competition_name": _competition_name(payload_json, candidate.competition_slug),
        "competition_slug": candidate.competition_slug,
        "updated_at": str(payload_json.get("reference_date") or source_payload.get("reference_date") or _candidate_date(candidate)),
        "playoff_type": source_payload.get("playoff_type"),
        "finished_matches": finished_matches,
        "pending_matches": pending_matches,
        "total_matches": total_matches,
        "rounds": visible_rounds,
        "layout": {
            "width": 1200,
            "height": height,
        },
    }


def _round_context(raw_round: dict[str, Any]) -> dict[str, Any]:
    matches = [match for match in raw_round.get("matches") or [] if isinstance(match, dict)]
    return {
        "label": str(raw_round.get("label") or "Fecha pendiente"),
        "matches": [_match_context(match) for match in matches],
    }


def _match_context(match: dict[str, Any]) -> dict[str, Any]:
    status = str(match.get("status") or "")
    score = match.get("score")
    if not score and match.get("home_score") is not None and match.get("away_score") is not None:
        score = f"{match.get('home_score')}-{match.get('away_score')}"
    return {
        "home_team": str(match.get("home_team") or "-"),
        "away_team": str(match.get("away_team") or "-"),
        "score": str(score or "vs"),
        "match_date": match.get("match_date"),
        "match_time": match.get("match_time"),
        "status": status,
        "is_finished": status == "finished",
    }


def _count_matches(rounds: list[dict[str, Any]]) -> int:
    return sum(len(row["matches"]) for row in rounds)


def _competition_name(payload_json: dict[str, Any], competition_slug: str) -> str:
    value = payload_json.get("competition_name")
    if isinstance(value, str) and value.strip():
        return value.strip()
    definition = load_competition_catalog().get(competition_slug)
    if definition is not None and definition.editorial_name:
        return definition.editorial_name
    if definition is not None:
        return definition.name
    return competition_slug


def _candidate_date(candidate: ContentCandidate) -> str:
    timestamp = candidate.published_at or candidate.created_at or candidate.updated_at
    if timestamp is None:
        return datetime.now().date().isoformat()
    return timestamp.date().isoformat()
