from __future__ import annotations

from app.schemas.standings_events import StandingsEventsGenerationResult, StandingsEventsResult


def render_standings_events(result: StandingsEventsResult) -> str:
    lines = [
        f"Standings Events | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"generated_at={result.generated_at.isoformat()}",
        f"current_snapshot={result.current_snapshot_timestamp.isoformat() if result.current_snapshot_timestamp else '-'}",
        f"previous_snapshot={result.previous_snapshot_timestamp.isoformat() if result.previous_snapshot_timestamp else '-'}",
        f"playoff_positions={result.playoff_positions or '-'}",
        f"relegation_positions={result.relegation_positions or '-'}",
        f"count={len(result.rows)}",
    ]
    if result.previous_snapshot_timestamp is None:
        lines.append("sin snapshot anterior; no se pueden detectar eventos de tabla")
        return "\n".join(lines)
    if not result.rows:
        lines.append("sin eventos detectados")
        return "\n".join(lines)

    lines.append("")
    for row in result.rows:
        position_delta = row.position_delta if row.position_delta is not None else "-"
        lines.append(
            f"- priority={row.priority} | type={row.event_type} | team={row.team} | "
            f"prev={row.previous_position or '-'} | curr={row.current_position or '-'} | "
            f"delta={position_delta} | {row.text_draft}"
        )
    return "\n".join(lines)


def render_standings_events_generation(result: StandingsEventsGenerationResult) -> str:
    header = [
        f"Standings Events | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"generated_at={result.generated_at.isoformat()}",
        f"found={result.stats.found}",
        f"inserted={result.stats.inserted}",
        f"updated={result.stats.updated}",
    ]
    if not result.rows:
        header.append("sin eventos generados")
        return "\n".join(header)
    return "\n".join(header) + "\n\n" + render_standings_events(result)
