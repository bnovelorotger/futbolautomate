from __future__ import annotations

import json
import sys

import typer

from app.channels.typefully.client import TypefullyApiError, TypefullyConfigurationError
from app.channels.typefully.publisher import TypefullyPublisherValidationError
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.session import init_db, session_scope
from app.presenters.typefully_export import (
    render_typefully_batch_result,
    render_typefully_config_status,
    render_typefully_result,
    render_typefully_rows,
)
from app.services.typefully_export_service import TypefullyExportService

app = typer.Typer(add_completion=False, help="Exportador de drafts a Typefully.")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _exit_error(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


def _prefer_rewrite(
    *,
    use_draft: bool,
    use_rewrite: bool,
) -> bool:
    if use_draft and use_rewrite:
        _exit_error("No puedes usar --use-draft y --use-rewrite a la vez")
    if use_draft:
        return False
    return True


@app.command("verify-config")
def verify_config(as_json: bool = typer.Option(False, "--json", help="Salida JSON")) -> None:
    payload = TypefullyExportService.config_status()
    if as_json:
        _dump_json(payload.model_dump(mode="json"))
    else:
        typer.echo(render_typefully_config_status(payload))
    if not payload.ready:
        raise typer.Exit(code=1)


@app.command("show-pending")
def show_pending(
    limit: int = typer.Option(50, min=1, help="Numero maximo de piezas"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Muestra la vista usando text_draft"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Muestra la vista priorizando rewritten_text"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    prefer_rewrite = _prefer_rewrite(use_draft=use_draft, use_rewrite=use_rewrite)
    with session_scope() as session:
        rows = TypefullyExportService(session).list_pending(limit=limit, prefer_rewrite=prefer_rewrite)
        if as_json:
            _dump_json([row.model_dump(mode="json") for row in rows])
        else:
            typer.echo(render_typefully_rows(rows))


@app.command("dry-run")
def dry_run_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza el uso de text_draft"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text si existe"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    prefer_rewrite = _prefer_rewrite(use_draft=use_draft, use_rewrite=use_rewrite)
    with session_scope() as session:
        service = TypefullyExportService(session)
        try:
            result = service.export_candidate(candidate_id, dry_run=True, prefer_rewrite=prefer_rewrite)
        except (
            TypefullyApiError,
            TypefullyConfigurationError,
            TypefullyPublisherValidationError,
            ConfigurationError,
            InvalidStateTransitionError,
        ) as exc:
            _exit_error(str(exc))
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_typefully_result(result))


@app.command("export")
def export_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza el uso de text_draft"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text si existe"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    prefer_rewrite = _prefer_rewrite(use_draft=use_draft, use_rewrite=use_rewrite)
    error_message: str | None = None
    result = None
    with session_scope() as session:
        service = TypefullyExportService(session)
        try:
            result = service.export_candidate(candidate_id, dry_run=False, prefer_rewrite=prefer_rewrite)
        except (
            TypefullyApiError,
            TypefullyConfigurationError,
            TypefullyPublisherValidationError,
            ConfigurationError,
            InvalidStateTransitionError,
        ) as exc:
            error_message = str(exc)
    if error_message:
        _exit_error(error_message)
    if as_json:
        _dump_json(result.model_dump(mode="json"))
    else:
        typer.echo(render_typefully_result(result))


@app.command("export-ready")
def export_ready(
    limit: int = typer.Option(20, min=1, help="Numero maximo de piezas"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No persiste external_publication_ref"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza el uso de text_draft"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text si existe"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    prefer_rewrite = _prefer_rewrite(use_draft=use_draft, use_rewrite=use_rewrite)
    with session_scope() as session:
        service = TypefullyExportService(session)
        try:
            result = service.export_ready(
                limit=limit,
                dry_run=dry_run,
                prefer_rewrite=prefer_rewrite,
            )
        except (
            TypefullyApiError,
            TypefullyConfigurationError,
            TypefullyPublisherValidationError,
            ConfigurationError,
            InvalidStateTransitionError,
        ) as exc:
            _exit_error(str(exc))
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_typefully_batch_result(result))


if __name__ == "__main__":
    app()
