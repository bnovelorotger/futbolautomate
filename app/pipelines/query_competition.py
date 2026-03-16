from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date

import typer

from app.core.enums import MatchWindow
from app.db.session import session_scope
from app.schemas.reporting import CompetitionMatchView, StandingView, TeamRankingView
from app.services.competition_queries import CompetitionQueryService

app = typer.Typer(add_completion=False, help="Consultas de explotacion sobre competiciones ya ingeridas.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _score_text(match: CompetitionMatchView) -> str:
    if match.home_score is not None and match.away_score is not None:
        return f"{match.home_score}-{match.away_score}"
    if match.match_time_raw:
        return match.match_time_raw
    return "-"


def _print_matches(matches: Iterable[CompetitionMatchView]) -> None:
    for match in matches:
        typer.echo(
            f"{match.round_name or '-'} | {match.match_date_raw or '-'} | "
            f"{_score_text(match)} | {match.home_team} vs {match.away_team} | {match.status}"
        )


def _print_standings(rows: Iterable[StandingView]) -> None:
    for row in rows:
        typer.echo(
            f"{row.position:>2} | {row.team} | pts={row.points} | pj={row.played} | "
            f"g={row.wins} e={row.draws} p={row.losses} | gf={row.goals_for} gc={row.goals_against} dg={row.goal_difference}"
        )


def _print_rankings(rows: Iterable[TeamRankingView], label: str) -> None:
    for row in rows:
        typer.echo(f"{row.position:>2} | {row.team} | {label}={row.value}")


@app.command("latest-results")
def latest_results(
    competition: str = typer.Option(..., help="Codigo interno de competicion"),
    limit: int = typer.Option(10, min=1, help="Numero maximo de resultados"),
    relevant_only: bool = typer.Option(
        False,
        "--relevant-only/--full-group",
        help="Filtrar solo partidos editorialmente relevantes para la competicion",
    ),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = CompetitionQueryService(session).latest_results(
            competition,
            limit=limit,
            relevant_only=relevant_only,
        )
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_matches(rows)


@app.command("standings")
def standings(
    competition: str = typer.Option(..., help="Codigo interno de competicion"),
    limit: int | None = typer.Option(None, min=1, help="Numero maximo de filas"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = CompetitionQueryService(session).current_standings(competition, limit=limit)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_standings(rows)


@app.command("upcoming")
def upcoming(
    competition: str = typer.Option(..., help="Codigo interno de competicion"),
    limit: int = typer.Option(10, min=1, help="Numero maximo de partidos"),
    relevant_only: bool = typer.Option(
        False,
        "--relevant-only/--full-group",
        help="Filtrar solo partidos editorialmente relevantes para la competicion",
    ),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = CompetitionQueryService(session).upcoming_matches(
            competition,
            limit=limit,
            relevant_only=relevant_only,
        )
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_matches(rows)


@app.command("round")
def round_matches(
    competition: str = typer.Option(..., help="Codigo interno de competicion"),
    round_name: str = typer.Option(..., "--round-name", help="Nombre o numero de jornada"),
    relevant_only: bool = typer.Option(
        False,
        "--relevant-only/--full-group",
        help="Filtrar solo partidos editorialmente relevantes para la competicion",
    ),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = CompetitionQueryService(session).matches_by_round(
            competition,
            round_name=round_name,
            relevant_only=relevant_only,
        )
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_matches(rows)


@app.command("top-attack")
def top_attack(
    competition: str = typer.Option(..., help="Codigo interno de competicion"),
    limit: int = typer.Option(5, min=1, help="Numero maximo de equipos"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = CompetitionQueryService(session).top_scoring_teams(competition, limit=limit)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_rankings(rows, "gf")


@app.command("top-defense")
def top_defense(
    competition: str = typer.Option(..., help="Codigo interno de competicion"),
    limit: int = typer.Option(5, min=1, help="Numero maximo de equipos"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = CompetitionQueryService(session).best_defense_teams(competition, limit=limit)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_rankings(rows, "gc")


@app.command("most-wins")
def most_wins(
    competition: str = typer.Option(..., help="Codigo interno de competicion"),
    limit: int = typer.Option(5, min=1, help="Numero maximo de equipos"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = CompetitionQueryService(session).most_wins_teams(competition, limit=limit)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_rankings(rows, "wins")


@app.command("window")
def window_matches(
    competition: str = typer.Option(..., help="Codigo interno de competicion"),
    window: MatchWindow = typer.Option(..., help="today, tomorrow o next_weekend"),
    reference_date: str | None = typer.Option(None, help="Fecha de referencia YYYY-MM-DD"),
    relevant_only: bool = typer.Option(
        False,
        "--relevant-only/--full-group",
        help="Filtrar solo partidos editorialmente relevantes para la competicion",
    ),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    parsed_reference_date = date.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        payload = CompetitionQueryService(session).matches_in_window(
            competition,
            window=window,
            reference_date=parsed_reference_date,
            relevant_only=relevant_only,
        )
        if as_json:
            _dump_json(payload.model_dump())
        else:
            typer.echo(f"{payload.window} | {payload.start_date} -> {payload.end_date}")
            _print_matches(payload.matches)


@app.command("summary")
def summary(
    competition: str = typer.Option(..., help="Codigo interno de competicion"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        payload = CompetitionQueryService(session).summary(competition)
        if as_json:
            _dump_json(payload.model_dump())
        else:
            typer.echo(f"competition={payload.competition_name} ({payload.competition_code})")
            typer.echo(f"total_teams={payload.total_teams}")
            typer.echo(f"total_matches={payload.total_matches}")
            typer.echo(f"played_matches={payload.played_matches}")
            typer.echo(f"pending_matches={payload.pending_matches}")


if __name__ == "__main__":
    app()
