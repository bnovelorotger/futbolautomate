from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date

import typer

from app.core.enums import SourceName
from app.db.session import session_scope
from app.schemas.reporting import NewsView
from app.services.news_queries import NewsQueryService

app = typer.Typer(add_completion=False, help="Consultas de explotacion sobre noticias ya ingeridas.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _print_news(rows: Iterable[NewsView]) -> None:
    for row in rows:
        published = row.published_at.isoformat() if row.published_at else "-"
        typer.echo(f"{published} | {row.source_name} | {row.news_type} | {row.title}")


@app.command("latest")
def latest(
    limit: int = typer.Option(10, min=1, help="Numero maximo de noticias"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = NewsQueryService(session).latest(limit=limit)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_news(rows)


@app.command("today")
def today(
    limit: int = typer.Option(20, min=1, help="Numero maximo de noticias"),
    reference_date: str | None = typer.Option(None, help="Fecha de referencia YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    parsed_reference_date = date.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        rows = NewsQueryService(session).today(limit=limit, reference_date=parsed_reference_date)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_news(rows)


@app.command("source")
def source_news(
    source: SourceName = typer.Option(..., help="Fuente de noticias"),
    limit: int = typer.Option(20, min=1, help="Numero maximo de noticias"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = NewsQueryService(session).by_source(source=source, limit=limit)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_news(rows)


@app.command("search")
def search(
    text: str = typer.Option(..., "--text", help="Texto a buscar en el titular"),
    limit: int = typer.Option(20, min=1, help="Numero maximo de noticias"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = NewsQueryService(session).search_titles(text=text, limit=limit)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_news(rows)


if __name__ == "__main__":
    app()
