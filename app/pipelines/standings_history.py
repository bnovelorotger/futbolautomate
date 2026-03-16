from __future__ import annotations

import json

import typer

from app.db.session import init_db, session_scope
from app.presenters.standings_history import render_standings_comparison, render_standings_snapshot
from app.services.standings_history import StandingsHistoryService

app = typer.Typer(
    add_completion=False,
    help="Inspeccion del historico de clasificacion por snapshots.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main() -> None:
    """CLI de snapshots historicos de clasificacion."""


@app.command("latest")
def latest_snapshot(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        result = StandingsHistoryService(session).latest_snapshot(competition_code)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_standings_snapshot(result))


@app.command("compare")
def compare_latest(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        result = StandingsHistoryService(session).compare_latest(competition_code)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_standings_comparison(result))


if __name__ == "__main__":
    app()
