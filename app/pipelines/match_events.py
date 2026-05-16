from __future__ import annotations

import json

import typer

from app.db.session import init_db, session_scope
from app.services.match_event_enricher import MatchEventEnricherService
from app.services.top_scorer_tracker import TopScorerTrackerService

app = typer.Typer(
    add_completion=False,
    help="Enriquecimiento batch de eventos de partido y ranking de goleadores.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _render_enrichment(result) -> str:
    lines = [
        f"checked={result.checked_count} enriched={result.enriched_count} events={result.total_events_found}",
    ]
    for row in result.rows:
        lines.append(
            f"- match_id={row.match_id} {row.home_team} vs {row.away_team} "
            f"events={row.events_found} persisted={row.persisted}"
        )
    return "\n".join(lines)


def _render_single_match(result) -> str:
    return (
        f"match_id={result.match_id} {result.home_team} vs {result.away_team} "
        f"events={result.events_found} persisted={result.persisted}"
    )


def _render_top_scorers(result) -> str:
    lines = [f"competition={result.competition_slug} rows={len(result.rows)}"]
    for index, row in enumerate(result.rows, start=1):
        lines.append(f"{index}. {row.player} ({row.team}) - {row.goals}")
    return "\n".join(lines)


@app.callback()
def main() -> None:
    """CLI de eventos de partido y goleadores."""


@app.command("enrich-pending")
def enrich_pending(
    competition_code: str | None = typer.Option(None, "--competition", help="Codigo interno de competicion"),
    limit: int = typer.Option(25, "--limit", min=1, help="Maximo de partidos a enriquecer"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No persiste cambios"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        result = MatchEventEnricherService(session).enrich_pending(
            limit=limit,
            competition_slug=competition_code,
            dry_run=dry_run,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(_render_enrichment(result))


@app.command("enrich-match")
def enrich_match(
    match_id: int = typer.Option(..., "--match-id", min=1, help="ID interno del partido"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No persiste cambios"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        result = MatchEventEnricherService(session).enrich_match(match_id, dry_run=dry_run)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(_render_single_match(result))


@app.command("top-scorers")
def top_scorers(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    limit: int = typer.Option(10, "--limit", min=1, help="Numero maximo de goleadores"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        result = TopScorerTrackerService(session).top_scorers_for_competition(competition_code, limit=limit)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(_render_top_scorers(result))


if __name__ == "__main__":
    app()
