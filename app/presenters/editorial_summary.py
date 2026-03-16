from __future__ import annotations

from collections.abc import Iterable

from app.schemas.editorial_summary import CompetitionEditorialSummary, EditorialSummaryNewsItem
from app.schemas.reporting import CompetitionMatchView, StandingView, TeamRankingView


def _score_or_time(match: CompetitionMatchView) -> str:
    if match.home_score is not None and match.away_score is not None:
        return f"{match.home_score}-{match.away_score}"
    if match.match_time_raw:
        return match.match_time_raw
    return "-"


def _append_matches(lines: list[str], title: str, matches: Iterable[CompetitionMatchView]) -> None:
    lines.append(title)
    rows = list(matches)
    if not rows:
        lines.append("- sin datos")
        lines.append("")
        return
    for match in rows:
        lines.append(
            f"- {match.round_name or '-'} | {match.match_date_raw or '-'} | {_score_or_time(match)} | "
            f"{match.home_team} vs {match.away_team} | {match.status}"
        )
    lines.append("")


def _append_standings(lines: list[str], rows: Iterable[StandingView]) -> None:
    lines.append("Clasificacion Actual")
    standings = list(rows)
    if not standings:
        lines.append("- sin clasificacion disponible")
        lines.append("")
        return
    for row in standings:
        lines.append(
            f"- {row.position}. {row.team} | pts={row.points} | pj={row.played} | "
            f"gf={row.goals_for} gc={row.goals_against} dg={row.goal_difference}"
        )
    lines.append("")


def _ranking_line(label: str, row: TeamRankingView | None) -> str:
    if row is None:
        return f"- {label}: sin datos"
    return f"- {label}: {row.team} ({row.value})"


def _append_news(lines: list[str], rows: Iterable[EditorialSummaryNewsItem]) -> None:
    lines.append("Noticias Editoriales Relevantes")
    news_items = list(rows)
    if not news_items:
        lines.append("- sin noticias relevantes")
        lines.append("")
        return
    for item in news_items:
        published_at = item.published_at.isoformat() if item.published_at else "-"
        clubs = ", ".join(item.clubs_detected or []) or "-"
        lines.append(
            f"- {published_at} | score={item.editorial_relevance_score} | motivo={item.selection_reason} | "
            f"competicion={item.competition_detected or '-'} | clubs={clubs} | {item.title}"
        )
    lines.append("")


def render_competition_summary(summary: CompetitionEditorialSummary) -> str:
    lines: list[str] = [
        f"Resumen Editorial | {summary.metadata.competition_name} ({summary.metadata.competition_slug})",
        f"reference_date={summary.metadata.reference_date.isoformat()}",
        f"generated_at={summary.metadata.generated_at.isoformat()}",
        "",
        "Estado General",
        f"- total_teams={summary.competition_state.total_teams}",
        f"- total_matches={summary.competition_state.total_matches}",
        f"- played_matches={summary.competition_state.played_matches}",
        f"- pending_matches={summary.competition_state.pending_matches}",
        "",
    ]

    _append_matches(lines, "Ultimos Resultados", summary.latest_results)
    _append_matches(lines, "Proximos Partidos", summary.upcoming_matches)
    _append_standings(lines, summary.current_standings)

    lines.extend(
        [
            "Rankings Destacados",
            _ranking_line("mejor_ataque", summary.rankings.best_attack),
            _ranking_line("mejor_defensa", summary.rankings.best_defense),
            _ranking_line("mas_victorias", summary.rankings.most_wins),
            "",
        ]
    )

    _append_matches(lines, "Ventana: Hoy", summary.calendar_windows.today)
    _append_matches(lines, "Ventana: Manana", summary.calendar_windows.tomorrow)
    _append_matches(lines, "Ventana: Proximo Fin de Semana", summary.calendar_windows.next_weekend)
    _append_news(lines, summary.editorial_news)

    lines.extend(
        [
            "Metricas Agregadas",
            f"- total_goals_scored={summary.aggregate_metrics.total_goals_scored}",
            f"- average_goals_per_played_match={summary.aggregate_metrics.average_goals_per_played_match}",
            f"- relevant_news_count={summary.aggregate_metrics.relevant_news_count}",
        ]
    )
    return "\n".join(lines)
