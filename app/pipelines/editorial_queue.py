from __future__ import annotations

import json
from datetime import datetime

import typer

from app.core.enums import ContentCandidateStatus, ContentType
from app.db.session import init_db, session_scope
from app.presenters.editorial_queue import (
    render_queue_detail,
    render_queue_rows,
    render_queue_summary,
)
from app.services.editorial_queue import EditorialQueueService

app = typer.Typer(add_completion=False, help="Cola editorial y flujo manual de revision.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("list")
def list_candidates(
    status: ContentCandidateStatus | None = typer.Option(None, help="Filtrar por estado"),
    competition: str | None = typer.Option(None, help="Filtrar por competicion"),
    content_type: ContentType | None = typer.Option(None, "--content-type", help="Filtrar por tipo"),
    priority_min: int | None = typer.Option(None, min=0, help="Prioridad minima"),
    limit: int = typer.Option(50, min=1, help="Numero maximo de filas"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        rows = EditorialQueueService(session).list_candidates(
            status=status,
            competition_slug=competition,
            content_type=content_type,
            priority_min=priority_min,
            limit=limit,
        )
        if as_json:
            _dump_json([row.model_dump(mode="json") for row in rows])
        else:
            typer.echo(render_queue_rows(rows))


@app.command("show")
def show_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        row = EditorialQueueService(session).get_candidate(candidate_id)
        if as_json:
            _dump_json(row.model_dump(mode="json"))
        else:
            typer.echo(render_queue_detail(row))


@app.command("approve")
def approve_candidate(candidate_id: int = typer.Option(..., "--id", help="ID del content candidate")) -> None:
    init_db()
    with session_scope() as session:
        row = EditorialQueueService(session).approve_candidate(candidate_id)
        typer.echo(render_queue_detail(row))


@app.command("reject")
def reject_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    reason: str | None = typer.Option(None, "--reason", help="Motivo opcional de rechazo"),
) -> None:
    init_db()
    with session_scope() as session:
        row = EditorialQueueService(session).reject_candidate(candidate_id, rejection_reason=reason)
        typer.echo(render_queue_detail(row))


@app.command("reset")
def reset_candidate(candidate_id: int = typer.Option(..., "--id", help="ID del content candidate")) -> None:
    init_db()
    with session_scope() as session:
        row = EditorialQueueService(session).reset_candidate(candidate_id)
        typer.echo(render_queue_detail(row))


@app.command("publish")
def publish_candidate(candidate_id: int = typer.Option(..., "--id", help="ID del content candidate")) -> None:
    init_db()
    with session_scope() as session:
        row = EditorialQueueService(session).publish_candidate(candidate_id)
        typer.echo(render_queue_detail(row))


@app.command("schedule")
def schedule_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    scheduled_at: str = typer.Option(..., "--scheduled-at", help="Fecha ISO con zona horaria"),
) -> None:
    init_db()
    parsed_scheduled_at = datetime.fromisoformat(scheduled_at)
    if parsed_scheduled_at.tzinfo is None:
        raise typer.BadParameter("scheduled-at debe incluir zona horaria")
    with session_scope() as session:
        row = EditorialQueueService(session).schedule_candidate(candidate_id, parsed_scheduled_at)
        typer.echo(render_queue_detail(row))


@app.command("summary")
def summary(as_json: bool = typer.Option(False, "--json", help="Salida JSON")) -> None:
    init_db()
    with session_scope() as session:
        payload = EditorialQueueService(session).summary()
        if as_json:
            _dump_json(payload.model_dump())
        else:
            typer.echo(render_queue_summary(payload))


if __name__ == "__main__":
    app()
