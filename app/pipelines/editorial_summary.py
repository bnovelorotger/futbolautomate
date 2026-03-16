from __future__ import annotations

import json
from datetime import date

import typer

from app.core.enums import OutputFormat
from app.db.session import session_scope
from app.presenters.editorial_summary import render_competition_summary
from app.services.editorial_summary import CompetitionEditorialSummaryService

app = typer.Typer(
    add_completion=False,
    help="Resumen editorial estructurado sobre competiciones ya ingeridas.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.callback()
def main() -> None:
    """CLI del motor de resumen editorial."""


@app.command("competition")
def competition(
    competition_code: str = typer.Option(..., "--competition", help="Codigo interno de competicion"),
    reference_date: str | None = typer.Option(None, help="Fecha de referencia YYYY-MM-DD"),
    results_limit: int = typer.Option(5, min=1, help="Numero maximo de ultimos resultados"),
    upcoming_limit: int = typer.Option(5, min=1, help="Numero maximo de proximos partidos"),
    news_limit: int = typer.Option(5, min=1, help="Numero maximo de noticias editoriales"),
    standings_limit: int = typer.Option(5, min=1, help="Numero maximo de equipos en clasificacion"),
    relevant_only: bool = typer.Option(
        True,
        "--relevant-only/--full-group",
        help="Filtrar partidos y ventanas al scope editorial relevante cuando la competicion lo requiera",
    ),
    output: OutputFormat = typer.Option(OutputFormat.CONSOLE, help="console o json"),
) -> None:
    parsed_reference_date = date.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        payload = CompetitionEditorialSummaryService(session).build_competition_summary(
            competition_code=competition_code,
            reference_date=parsed_reference_date,
            results_limit=results_limit,
            upcoming_limit=upcoming_limit,
            news_limit=news_limit,
            standings_limit=standings_limit,
            relevant_only=relevant_only,
        )
        if output == OutputFormat.JSON:
            _dump_json(payload.model_dump(mode="json"))
        else:
            typer.echo(render_competition_summary(payload))


if __name__ == "__main__":
    app()
