from __future__ import annotations

import json

import typer

from app.channels.x.auth import XAuthError
from app.channels.x.client import XApiError
from app.channels.x.publisher import XPublisherValidationError
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.session import init_db, session_scope
from app.presenters.x_publication import render_x_batch_result, render_x_result, render_x_rows
from app.services.x_publication_service import XPublicationService

app = typer.Typer(add_completion=False, help="Adaptador de publicacion externa en X.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _exit_error(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)

@app.command("show-pending")
def show_pending(
    limit: int = typer.Option(50, min=1, help="Numero maximo de piezas"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        rows = XPublicationService(session).list_pending(limit=limit)
        if as_json:
            _dump_json([row.model_dump(mode="json") for row in rows])
        else:
            typer.echo(render_x_rows(rows))


@app.command("dry-run")
def dry_run_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        service = XPublicationService(session)
        try:
            result = service.publish_candidate(candidate_id, dry_run=True)
        except (
            XAuthError,
            XApiError,
            XPublisherValidationError,
            ConfigurationError,
            InvalidStateTransitionError,
        ) as exc:
            _exit_error(str(exc))
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_x_result(result))


@app.command("publish")
def publish_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    error_message: str | None = None
    result = None
    with session_scope() as session:
        service = XPublicationService(session)
        try:
            result = service.publish_candidate(candidate_id, dry_run=False)
        except (
            XAuthError,
            XApiError,
            XPublisherValidationError,
            ConfigurationError,
            InvalidStateTransitionError,
        ) as exc:
            error_message = str(exc)
    if error_message:
        _exit_error(error_message)
    if as_json:
        _dump_json(result.model_dump(mode="json"))
    else:
        typer.echo(render_x_result(result))


@app.command("publish-pending")
def publish_pending(
    limit: int = typer.Option(20, min=1, help="Numero maximo de piezas"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No persiste external_publication_ref"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        service = XPublicationService(session)
        try:
            result = service.publish_pending(limit=limit, dry_run=dry_run)
        except (
            XAuthError,
            XApiError,
            XPublisherValidationError,
            ConfigurationError,
            InvalidStateTransitionError,
        ) as exc:
            _exit_error(str(exc))
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_x_batch_result(result))


if __name__ == "__main__":
    app()
