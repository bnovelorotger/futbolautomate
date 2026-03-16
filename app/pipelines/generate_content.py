from __future__ import annotations

import json
from datetime import date

import typer

from app.core.config import get_settings
from app.core.enums import OutputFormat
from app.core.logging import configure_logging
from app.db.session import init_db, session_scope
from app.presenters.content_candidates import render_content_generation_result
from app.services.editorial_content_generator import EditorialContentGenerator

app = typer.Typer(
    add_completion=False,
    help="Generador de borradores editoriales estructurados a partir de editorial_summary.",
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.callback(invoke_without_command=True)
def main(
    competition: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, help="Fecha de referencia YYYY-MM-DD"),
    relevant_only: bool = typer.Option(
        True,
        "--relevant-only/--full-group",
        help="Filtrar partidos y ventanas al scope editorial relevante cuando la competicion lo requiera",
    ),
    results_limit: int = typer.Option(5, min=1, help="Numero maximo de resultados a convertir en borradores"),
    upcoming_limit: int = typer.Option(5, min=1, help="Numero maximo de partidos proximos para la previa"),
    news_limit: int = typer.Option(5, min=1, help="Numero maximo de noticias en el resumen fuente"),
    standings_limit: int = typer.Option(5, min=1, help="Numero maximo de equipos en la clasificacion fuente"),
    output: OutputFormat = typer.Option(OutputFormat.CONSOLE, help="console o json"),
) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_db()
    parsed_reference_date = date.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = EditorialContentGenerator(session).generate_for_competition(
            competition_code=competition,
            reference_date=parsed_reference_date,
            relevant_only=relevant_only,
            results_limit=results_limit,
            upcoming_limit=upcoming_limit,
            news_limit=news_limit,
            standings_limit=standings_limit,
        )
        if output == OutputFormat.JSON:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_content_generation_result(result))


if __name__ == "__main__":
    app()
