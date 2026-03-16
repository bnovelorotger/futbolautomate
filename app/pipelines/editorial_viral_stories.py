from __future__ import annotations

import json
from datetime import date as date_type

import typer

from app.db.session import init_db, session_scope
from app.presenters.editorial_viral_stories import (
    render_editorial_viral_stories,
    render_editorial_viral_stories_generation,
)
from app.services.editorial_viral_stories import EditorialViralStoriesService

app = typer.Typer(
    add_completion=False,
    help="Historias virales editoriales basadas en datos reales de competicion.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main() -> None:
    """CLI de historias virales editoriales."""


@app.command("show")
def show_competition(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, "--date", help="Fecha de referencia YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = EditorialViralStoriesService(session).preview_for_competition(
            competition_code,
            reference_date=parsed_date,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_editorial_viral_stories(result))


@app.command("generate")
def generate_competition(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, "--date", help="Fecha de referencia YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = EditorialViralStoriesService(session).generate_for_competition(
            competition_code,
            reference_date=parsed_date,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_editorial_viral_stories_generation(result))


if __name__ == "__main__":
    app()
