from __future__ import annotations

import json
from datetime import datetime

import typer

from app.db.session import init_db, session_scope
from app.presenters.publication_dispatch import (
    render_dispatch_result,
    render_dispatch_rows,
    render_dispatch_summary,
)
from app.services.publication_dispatcher import PublicationDispatcherService

app = typer.Typer(add_completion=False, help="Despachador interno de piezas listas para publicacion.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise typer.BadParameter("la fecha debe incluir zona horaria")
    return parsed


@app.command("list-ready")
def list_ready(
    now: str | None = typer.Option(None, help="Fecha ISO con zona horaria para evaluar elegibilidad"),
    include_unscheduled: bool = typer.Option(
        True,
        "--include-unscheduled/--scheduled-only",
        help="Incluir piezas aprobadas sin scheduled_at",
    ),
    limit: int = typer.Option(50, min=1, help="Numero maximo de piezas"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    reference = _parse_datetime(now)
    with session_scope() as session:
        rows = PublicationDispatcherService(session).list_ready(
            now=reference,
            include_unscheduled=include_unscheduled,
            limit=limit,
        )
        if as_json:
            _dump_json([row.model_dump(mode="json") for row in rows])
        else:
            typer.echo(render_dispatch_rows(rows))


@app.command("dispatch")
def dispatch(
    now: str | None = typer.Option(None, help="Fecha ISO con zona horaria para evaluar elegibilidad"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No modifica el estado"),
    include_unscheduled: bool = typer.Option(
        False,
        "--include-unscheduled/--scheduled-only",
        help="Permite despachar piezas aprobadas sin scheduled_at",
    ),
    limit: int = typer.Option(20, min=1, help="Numero maximo de piezas a despachar"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    reference = _parse_datetime(now)
    with session_scope() as session:
        result = PublicationDispatcherService(session).dispatch(
            now=reference,
            limit=limit,
            dry_run=dry_run,
            include_unscheduled=include_unscheduled,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_dispatch_result(result))


@app.command("publish")
def publish_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    published_at: str | None = typer.Option(None, "--published-at", help="Marca temporal ISO con zona horaria"),
    external_ref: str | None = typer.Option(None, "--external-ref", help="Referencia futura externa opcional"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    reference = _parse_datetime(published_at)
    with session_scope() as session:
        row = PublicationDispatcherService(session).publish_candidate(
            candidate_id,
            published_at=reference,
            external_publication_ref=external_ref,
        )
        if as_json:
            _dump_json(row.model_dump(mode="json"))
        else:
            typer.echo(render_dispatch_rows([row]))


@app.command("summary")
def summary(
    now: str | None = typer.Option(None, help="Fecha ISO con zona horaria para evaluar elegibilidad"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    reference = _parse_datetime(now)
    with session_scope() as session:
        payload = PublicationDispatcherService(session).summary(now=reference)
        if as_json:
            _dump_json(payload.model_dump())
        else:
            typer.echo(render_dispatch_summary(payload))


if __name__ == "__main__":
    app()
