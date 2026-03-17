from __future__ import annotations

import json
from datetime import date as date_type

import typer

from app.db.session import init_db, session_scope
from app.presenters.results_roundup import (
    render_results_roundup,
    render_results_roundup_generation,
)
from app.services.results_roundup import ResultsRoundupService

app = typer.Typer(
    add_completion=False,
    help="Agrupador editorial de resultados por jornada o bloque.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main() -> None:
    """CLI de results_roundup."""


@app.command("show")
def show_competition(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, "--date", help="Fecha YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = ResultsRoundupService(session).show_for_competition(
            competition_code,
            reference_date=parsed_date,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_results_roundup(result))


@app.command("generate")
def generate_competition(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, "--date", help="Fecha YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = ResultsRoundupService(session).generate_for_competition(
            competition_code,
            reference_date=parsed_date,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_results_roundup_generation(result))


if __name__ == "__main__":
    app()
