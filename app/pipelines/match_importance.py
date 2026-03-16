from __future__ import annotations

import json
from datetime import date as date_type

import typer

from app.db.session import init_db, session_scope
from app.presenters.match_importance import (
    render_match_importance,
    render_match_importance_generation,
)
from app.services.match_importance import MatchImportanceService

app = typer.Typer(
    add_completion=False,
    help="Detector editorial de partidos destacados.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main() -> None:
    """CLI de importancia de partido."""


@app.command("show")
def show_competition(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, "--date", help="Fecha de referencia YYYY-MM-DD"),
    limit: int | None = typer.Option(None, "--limit", help="Limitar numero de partidos mostrados"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = MatchImportanceService(session).show_for_competition(
            competition_code,
            reference_date=parsed_date,
            limit=limit,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_match_importance(result))


@app.command("top")
def top_competition(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, "--date", help="Fecha de referencia YYYY-MM-DD"),
    limit: int = typer.Option(5, "--limit", help="Numero maximo de partidos"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = MatchImportanceService(session).top_for_competition(
            competition_code,
            reference_date=parsed_date,
            limit=limit,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_match_importance(result))


@app.command("generate")
def generate_competition(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, "--date", help="Fecha de referencia YYYY-MM-DD"),
    limit: int = typer.Option(3, "--limit", help="Numero maximo de partidos a convertir en drafts"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = MatchImportanceService(session).generate_for_competition(
            competition_code,
            reference_date=parsed_date,
            limit=limit,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_match_importance_generation(result))


if __name__ == "__main__":
    app()
