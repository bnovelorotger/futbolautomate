from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, object_session

from app.core.catalog import load_competition_catalog
from app.core.exceptions import ConfigurationError
from app.core.standings_zones import load_standings_zones
from app.db.models import ContentCandidate
from app.schemas.reporting import StandingView
from app.services.competition_queries import CompetitionQueryService
from app.services.competition_relevance import CompetitionRelevanceService

_DEFAULT_WIDTH = 1200
_DEFAULT_HEIGHT = 1500
_DEFAULT_OUTER_PADDING = 34
_DEFAULT_FRAME_PADDING = 34
_DEFAULT_SECTION_GAP = 24
_DEFAULT_SIDE_WIDTH = 220


def build_standings_image_context(
    candidate: ContentCandidate,
    max_rows: int | None = None,
    *,
    session: Session | None = None,
) -> dict[str, Any]:
    payload_json = candidate.payload_json if isinstance(candidate.payload_json, dict) else {}
    source_payload = payload_json.get("source_payload") if isinstance(payload_json.get("source_payload"), dict) else {}
    competition_slug = candidate.competition_slug

    standings_rows = _standings_rows(candidate, session=session)
    total_teams = len(standings_rows)
    if standings_rows:
        rows = _map_reporting_rows(competition_slug, standings_rows, max_rows=max_rows)
    else:
        payload_rows = _map_payload_rows(
            competition_slug,
            source_payload.get("rows"),
            max_rows=None,
        )
        total_teams = len(payload_rows)
        rows = _limit_rows(payload_rows, max_rows=max_rows)

    columns = _column_flags(rows)
    layout = _layout_config(row_count=len(rows), columns=columns)
    tracked_teams_present = _tracked_teams_present(competition_slug, [row["team_name"] for row in rows])

    round_label = _string(source_payload.get("round_name")) or _string(source_payload.get("group_label"))
    group_label = _string(source_payload.get("group_label")) or _string(payload_json.get("group_label"))
    if group_label == round_label:
        group_label = None

    season_label = (
        _string(payload_json.get("season_label"))
        or _string(payload_json.get("season"))
        or _string(source_payload.get("season_label"))
        or _string(source_payload.get("season"))
        or _competition_season(competition_slug)
    )
    updated_at = (
        _string(payload_json.get("reference_date"))
        or _string(source_payload.get("reference_date"))
        or _candidate_date(candidate)
    )

    return {
        "title": "CLASIFICACI\u00d3N",
        "competition_name": _competition_name(payload_json, competition_slug),
        "competition_slug": competition_slug,
        "round_label": round_label,
        "updated_at": updated_at,
        "season_label": season_label,
        "group_label": group_label,
        "rows": rows,
        "total_teams": total_teams,
        "visible_rows": len(rows),
        "tracked_teams_present": tracked_teams_present,
        "has_tracked_teams": bool(tracked_teams_present),
        "legend": {
            "leader": {"short": "1\u00ba", "label": "L\u00edder"},
            "playoff": {"short": "PO", "label": "Playoff"},
            "relegation": {"short": "DESC", "label": "Descenso"},
            "tracked": {"label": "Equipo seguido"},
        },
        "layout": layout,
        "columns": columns,
    }


def _standings_rows(candidate: ContentCandidate, *, session: Session | None) -> list[StandingView]:
    bound_session = session or object_session(candidate)
    if bound_session is None:
        return []
    try:
        return CompetitionQueryService(bound_session).current_standings(candidate.competition_slug)
    except ConfigurationError:
        return []


def _map_reporting_rows(
    competition_slug: str,
    standings: list[StandingView],
    *,
    max_rows: int | None,
) -> list[dict[str, Any]]:
    rows = [
        _standings_row(
            competition_slug,
            position=row.position,
            team_name=row.team,
            points=row.points,
            played=row.played,
            won=row.wins,
            drawn=row.draws,
            lost=row.losses,
            goal_diff=row.goal_difference,
        )
        for row in standings
    ]
    return _limit_rows(rows, max_rows=max_rows)


def _map_payload_rows(
    competition_slug: str,
    raw_rows: Any,
    *,
    max_rows: int | None,
) -> list[dict[str, Any]]:
    rows = [
        mapped_row
        for raw_row in (raw_rows if isinstance(raw_rows, list) else [])
        for mapped_row in [_map_payload_row(competition_slug, raw_row)]
        if mapped_row is not None
    ]
    return _limit_rows(sorted(rows, key=lambda row: row["position"]), max_rows=max_rows)


def _map_payload_row(competition_slug: str, raw_row: Any) -> dict[str, Any] | None:
    if not isinstance(raw_row, dict):
        return None

    position = _int(raw_row.get("position"))
    team_name = _string(raw_row.get("team_name")) or _string(raw_row.get("team"))
    if position is None or team_name is None:
        return None

    zone = _normalize_zone(raw_row.get("zone")) or _normalize_zone(raw_row.get("zone_tag")) or _zone_for_position(
        competition_slug,
        position,
    )
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
        "is_leader": position == 1,
        "is_tracked_team": _is_tracked_team(competition_slug, team_name),
    }


def _standings_row(
    competition_slug: str,
    *,
    position: int,
    team_name: str,
    points: int | None,
    played: int | None,
    won: int | None,
    drawn: int | None,
    lost: int | None,
    goal_diff: int | None,
) -> dict[str, Any]:
    return {
        "position": position,
        "team_name": team_name,
        "points": points,
        "played": played,
        "won": won,
        "drawn": drawn,
        "lost": lost,
        "goal_diff": goal_diff,
        "zone": _zone_for_position(competition_slug, position),
        "is_leader": position == 1,
        "is_tracked_team": _is_tracked_team(competition_slug, team_name),
    }


def _limit_rows(rows: list[dict[str, Any]], *, max_rows: int | None) -> list[dict[str, Any]]:
    if max_rows is None:
        return rows
    return rows[: max(0, int(max_rows))]


def _zone_for_position(competition_slug: str, position: int) -> str | None:
    zone_config = load_standings_zones().get(competition_slug)
    playoff_positions = set(zone_config.playoff_positions if zone_config is not None else [])
    relegation_positions = set(zone_config.relegation_positions if zone_config is not None else [])
    if position in playoff_positions:
        return "playoff"
    if position in relegation_positions:
        return "relegation"
    return None


def _column_flags(rows: list[dict[str, Any]]) -> dict[str, bool]:
    return {
        "won": any(row["won"] is not None for row in rows),
        "drawn": any(row["drawn"] is not None for row in rows),
        "lost": any(row["lost"] is not None for row in rows),
        "goal_diff": any(row["goal_diff"] is not None for row in rows),
    }


def _layout_config(*, row_count: int, columns: dict[str, bool]) -> dict[str, Any]:
    stat_columns = sum(1 for enabled in columns.values() if enabled)
    density = row_count + max(0, stat_columns - 1) * 2

    if density >= 24:
        row_height = 44
        table_font_size = 17
        position_font_size = 22
        points_font_size = 22
        title_font_size = 40
        header_font_size = 11
        meta_font_size = 13
        side_width = 192
        outer_padding = 20
        frame_padding = 24
        section_gap = 16
    elif density >= 20:
        row_height = 48
        table_font_size = 18
        position_font_size = 24
        points_font_size = 24
        title_font_size = 42
        header_font_size = 12
        meta_font_size = 13
        side_width = 196
        outer_padding = 22
        frame_padding = 24
        section_gap = 18
    elif density >= 16:
        row_height = 52
        table_font_size = 19
        position_font_size = 26
        points_font_size = 25
        title_font_size = 46
        header_font_size = 13
        meta_font_size = 14
        side_width = 206
        outer_padding = 26
        frame_padding = 28
        section_gap = 20
    else:
        row_height = 58
        table_font_size = 20
        position_font_size = 28
        points_font_size = 27
        title_font_size = 50
        header_font_size = 14
        meta_font_size = 15
        side_width = _DEFAULT_SIDE_WIDTH
        outer_padding = _DEFAULT_OUTER_PADDING
        frame_padding = _DEFAULT_FRAME_PADDING
        section_gap = _DEFAULT_SECTION_GAP

    table_head_height = 48 if density >= 20 else 54 if density >= 16 else 60
    height = max(
        _DEFAULT_HEIGHT,
        320 + table_head_height + row_count * row_height + (outer_padding + frame_padding) * 2 + section_gap * 2,
    )

    return {
        "width": _DEFAULT_WIDTH,
        "height": height,
        "max_rows": row_count,
        "row_height": row_height,
        "table_head_height": table_head_height,
        "table_font_size": table_font_size,
        "position_font_size": position_font_size,
        "points_font_size": points_font_size,
        "title_font_size": title_font_size,
        "header_font_size": header_font_size,
        "meta_font_size": meta_font_size,
        "side_width": side_width,
        "outer_padding": outer_padding,
        "frame_padding": frame_padding,
        "section_gap": section_gap,
        "table_grid_columns": _grid_template_columns(columns),
    }


def _grid_template_columns(columns: dict[str, bool]) -> str:
    parts = ["58px", "minmax(0, 2.8fr)", "68px", "62px"]
    if columns["won"]:
        parts.append("54px")
    if columns["drawn"]:
        parts.append("54px")
    if columns["lost"]:
        parts.append("54px")
    if columns["goal_diff"]:
        parts.append("68px")
    parts.append("84px")
    return " ".join(parts)


def _competition_name(payload_json: dict[str, Any], competition_slug: str) -> str:
    if _string(payload_json.get("competition_name")) is not None:
        return str(payload_json["competition_name"]).strip()
    competition = load_competition_catalog().get(competition_slug)
    if competition is not None and competition.editorial_name:
        return competition.editorial_name
    if competition is not None:
        return competition.name
    return _humanize_slug(competition_slug)


def _competition_season(competition_slug: str) -> str | None:
    competition = load_competition_catalog().get(competition_slug)
    if competition is None:
        return None
    return _string(competition.season)


def _tracked_teams_present(competition_slug: str, team_names: list[str]) -> list[str]:
    try:
        return CompetitionRelevanceService().tracked_teams_present(competition_slug, team_names)
    except ConfigurationError:
        return []


def _is_tracked_team(competition_slug: str, team_name: str | None) -> bool:
    try:
        return CompetitionRelevanceService().is_tracked_team(competition_slug, team_name)
    except ConfigurationError:
        return False


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
