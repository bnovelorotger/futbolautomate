from __future__ import annotations

from app.schemas.team_form import TeamFormGenerationResult, TeamFormResult


def render_team_form_show(result: TeamFormResult) -> str:
    lines = [
        f"Team Form | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"window_size={result.window_size}",
        f"generated_at={result.generated_at.isoformat()}",
        f"count={len(result.rows)}",
    ]
    if not result.rows:
        lines.append("sin datos de forma disponibles")
        return "\n".join(lines)

    lines.append("")
    for row in result.rows:
        lines.append(
            f"- {row.rank}. {row.team} | seq={row.sequence} | pts={row.points} | "
            f"gf={row.goals_for} | gc={row.goals_against} | dg={row.goal_difference} | "
            f"w={row.wins} d={row.draws} l={row.losses}"
        )
    return "\n".join(lines)


def render_team_form_ranking(result: TeamFormResult) -> str:
    lines = [
        f"Form Ranking | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"window_size={result.window_size}",
        f"generated_at={result.generated_at.isoformat()}",
        f"count={len(result.rows)}",
    ]
    if not result.rows:
        lines.append("sin ranking de forma disponible")
        return "\n".join(lines)

    lines.append("")
    for row in result.rows:
        lines.append(f"{row.rank}. {row.team} -> {row.sequence} ({row.points} pts)")

    lines.append("")
    lines.append(f"events={len(result.events)}")
    for event in result.events:
        lines.append(f"- {event.event_type} | {event.team} | {event.text_draft}")
    return "\n".join(lines)


def render_team_form_generation(result: TeamFormGenerationResult) -> str:
    header = [
        f"Team Form | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"window_size={result.window_size}",
        f"generated_at={result.generated_at.isoformat()}",
        f"found={result.stats.found}",
        f"inserted={result.stats.inserted}",
        f"updated={result.stats.updated}",
    ]
    if not result.rows and not result.events:
        header.append("sin content candidates generados")
        return "\n".join(header)
    return "\n".join(header) + "\n\n" + render_team_form_ranking(result)
