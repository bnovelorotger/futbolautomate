from __future__ import annotations

import json

import typer

from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.session import init_db, session_scope
from app.llm.providers.base import LLMConfigurationError, LLMProviderError
from app.presenters.editorial_rewrite import (
    render_rewrite_batch_result,
    render_rewrite_detail,
    render_rewrite_result,
)
from app.services.editorial_rewriter import EditorialRewriterService

app = typer.Typer(add_completion=False, help="Reescritura editorial opcional con LLM.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _exit_error(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


@app.command("show")
def show_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        try:
            payload = EditorialRewriterService(session).show_candidate(candidate_id)
        except ConfigurationError as exc:
            _exit_error(str(exc))
        if as_json:
            _dump_json(payload.model_dump(mode="json"))
        else:
            typer.echo(render_rewrite_detail(payload))


@app.command("dry-run")
def dry_run_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Permite recalcular aunque ya exista rewritten_text"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        service = EditorialRewriterService(session)
        try:
            payload = service.rewrite_candidate(candidate_id, dry_run=True, overwrite=overwrite)
        except (
            LLMConfigurationError,
            LLMProviderError,
            ConfigurationError,
            InvalidStateTransitionError,
        ) as exc:
            _exit_error(str(exc))
        if as_json:
            _dump_json(payload.model_dump(mode="json"))
        else:
            typer.echo(render_rewrite_result(payload))


@app.command("rewrite")
def rewrite_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Permite reemplazar rewritten_text existente"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    error_message: str | None = None
    result = None
    with session_scope() as session:
        service = EditorialRewriterService(session)
        try:
            result = service.rewrite_candidate(candidate_id, dry_run=False, overwrite=overwrite)
        except (
            LLMConfigurationError,
            LLMProviderError,
            ConfigurationError,
            InvalidStateTransitionError,
        ) as exc:
            error_message = str(exc)
    if error_message:
        _exit_error(error_message)
    if as_json:
        _dump_json(result.model_dump(mode="json"))
    else:
        typer.echo(render_rewrite_result(result))


@app.command("rewrite-pending")
def rewrite_pending(
    limit: int = typer.Option(10, min=1, help="Numero maximo de candidatos"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No persiste rewritten_text"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Permite reemplazar rewritten_text existente"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        service = EditorialRewriterService(session)
        try:
            payload = service.rewrite_pending(limit=limit, dry_run=dry_run, overwrite=overwrite)
        except (
            LLMConfigurationError,
            LLMProviderError,
            ConfigurationError,
            InvalidStateTransitionError,
        ) as exc:
            _exit_error(str(exc))
        if as_json:
            _dump_json(payload.model_dump(mode="json"))
        else:
            typer.echo(render_rewrite_batch_result(payload))


if __name__ == "__main__":
    app()
