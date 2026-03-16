from __future__ import annotations

import json
from datetime import date as date_type

import typer

from app.db.session import init_db, session_scope
from app.presenters.team_form import (
    render_team_form_generation,
    render_team_form_ranking,
    render_team_form_show,
)
from app.services.team_form import TeamFormService

app = typer.Typer(
    add_completion=False,
    help="Analisis de forma reciente por competicion basado en partidos reales.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main() -> None:
    """CLI de forma reciente de equipos."""


@app.command("show")
def show_competition(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, "--date", help="Fecha de referencia YYYY-MM-DD"),
    window_size: int = typer.Option(5, "--window", help="Numero de partidos recientes"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = TeamFormService(session).preview_for_competition(
            competition_code,
            window_size=window_size,
            reference_date=parsed_date,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_team_form_show(result))


@app.command("ranking")
def ranking_competition(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, "--date", help="Fecha de referencia YYYY-MM-DD"),
    window_size: int = typer.Option(5, "--window", help="Numero de partidos recientes"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = TeamFormService(session).ranking_for_competition(
            competition_code,
            window_size=window_size,
            reference_date=parsed_date,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_team_form_ranking(result))


@app.command("generate")
def generate_competition(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, "--date", help="Fecha de referencia YYYY-MM-DD"),
    window_size: int = typer.Option(5, "--window", help="Numero de partidos recientes"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = TeamFormService(session).generate_for_competition(
            competition_code,
            window_size=window_size,
            reference_date=parsed_date,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_team_form_generation(result))


if __name__ == "__main__":
    app()
