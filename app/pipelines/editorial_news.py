from __future__ import annotations

import json

import typer

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import init_db, session_scope
from app.schemas.reporting import EditorialNewsView
from app.services.news_editorial import enrich_news_editorial
from app.services.news_editorial_queries import NewsEditorialQueryService

app = typer.Typer(add_completion=False, help="Enriquecimiento y consultas editoriales sobre noticias.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _print_rows(rows: list[EditorialNewsView]) -> None:
    for row in rows:
        clubs = ", ".join(row.clubs_detected or [])
        typer.echo(
            f"{row.editorial_relevance_score:>3} | {row.source_name} | {row.sport_detected or '-'} | "
            f"balearic={row.is_balearic_related} | clubs={clubs or '-'} | "
            f"{row.competition_detected or '-'} | {row.title}"
        )


@app.command("enrich")
def enrich(
    limit: int | None = typer.Option(None, min=1, help="Numero maximo de noticias"),
    source: str | None = typer.Option(None, help="Fuente opcional"),
) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_db()
    with session_scope() as session:
        stats = enrich_news_editorial(session, limit=limit, source_name=source)
        typer.echo(
            f"found={stats.found} inserted={stats.inserted} updated={stats.updated} errors={stats.errors}"
        )


@app.command("relevant")
def relevant(
    limit: int = typer.Option(20, min=1, help="Numero maximo de noticias"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = NewsEditorialQueryService(session).relevant_balearic_football(limit=limit)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_rows(rows)


@app.command("non-balearic")
def non_balearic(
    limit: int = typer.Option(20, min=1, help="Numero maximo de noticias"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = NewsEditorialQueryService(session).football_non_balearic(limit=limit)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_rows(rows)


@app.command("club")
def club(
    club_name: str = typer.Option(..., "--club", help="Club detectado"),
    limit: int = typer.Option(20, min=1, help="Numero maximo de noticias"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = NewsEditorialQueryService(session).by_club(club=club_name, limit=limit)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_rows(rows)


@app.command("competition")
def competition(
    competition_name: str = typer.Option(..., "--competition", help="Competicion detectada"),
    limit: int = typer.Option(20, min=1, help="Numero maximo de noticias"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = NewsEditorialQueryService(session).by_competition(
            competition=competition_name,
            limit=limit,
        )
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_rows(rows)


@app.command("top")
def top(
    limit: int = typer.Option(20, min=1, help="Numero maximo de noticias"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    with session_scope() as session:
        rows = NewsEditorialQueryService(session).top_scores(limit=limit)
        if as_json:
            _dump_json([row.model_dump() for row in rows])
        else:
            _print_rows(rows)


@app.command("summary")
def summary(as_json: bool = typer.Option(False, "--json", help="Salida JSON")) -> None:
    with session_scope() as session:
        payload = NewsEditorialQueryService(session).summary_counts()
        if as_json:
            _dump_json(payload.model_dump())
        else:
            typer.echo(f"relevant_balearic_football={payload.relevant_balearic_football}")
            typer.echo(f"football_non_balearic={payload.football_non_balearic}")
            typer.echo(f"other_sports_or_unknown={payload.other_sports_or_unknown}")


if __name__ == "__main__":
    app()
