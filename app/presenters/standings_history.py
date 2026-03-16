from __future__ import annotations

from app.schemas.standings_history import StandingsComparisonView, StandingsSnapshotView


def render_standings_snapshot(result: StandingsSnapshotView) -> str:
    lines = [
        f"Standings Snapshot | {result.competition_name} ({result.competition_slug})",
        f"source={result.source_name}",
        f"snapshot_date={result.snapshot_date.isoformat()}",
        f"snapshot_timestamp={result.snapshot_timestamp.isoformat()}",
        f"count={len(result.rows)}",
    ]
    if not result.rows:
        lines.append("sin filas en el snapshot")
        return "\n".join(lines)

    lines.append("")
    for row in result.rows:
        lines.append(
            f"- {row.position:>2} | {row.team} | pts={row.points or '-'} | pj={row.played or '-'} | "
            f"gf={row.goals_for or '-'} | gc={row.goals_against or '-'} | dg={row.goal_difference or '-'}"
        )
    return "\n".join(lines)


def render_standings_comparison(result: StandingsComparisonView) -> str:
    lines = [
        f"Standings Compare | {result.competition_name} ({result.competition_slug})",
        f"current_snapshot={result.current_snapshot_timestamp.isoformat()}",
        f"previous_snapshot={result.previous_snapshot_timestamp.isoformat() if result.previous_snapshot_timestamp else '-'}",
        f"count={len(result.rows)}",
    ]
    if result.previous_snapshot_timestamp is None:
        lines.append("sin snapshot anterior para comparar")
        return "\n".join(lines)
    if not result.rows:
        lines.append("sin filas para comparar")
        return "\n".join(lines)

    lines.append("")
    for row in result.rows:
        position_delta = row.position_delta if row.position_delta is not None else "-"
        points_delta = row.points_delta if row.points_delta is not None else "-"
        lines.append(
            f"- {row.team} | prev={row.previous_position or '-'} | curr={row.current_position or '-'} | "
            f"pos_delta={position_delta} | pts_prev={row.previous_points or '-'} | "
            f"pts_curr={row.current_points or '-'} | pts_delta={points_delta}"
        )
    return "\n".join(lines)
