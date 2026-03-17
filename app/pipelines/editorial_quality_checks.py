from __future__ import annotations

import json
import sys
from datetime import date as date_type

import typer

from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.session import init_db, session_scope
from app.presenters.editorial_quality_checks import (
    render_quality_batch_result,
    render_quality_result,
)
from app.services.editorial_quality_checks import EditorialQualityChecksService

app = typer.Typer(add_completion=False, help="Checks editoriales deterministas previos a la autoexportacion.")

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


@app.command("check")
def check_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza text_draft"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    prefer_rewrite = _prefer_rewrite(use_draft=use_draft, use_rewrite=use_rewrite)
    error_message: str | None = None
    result = None
    with session_scope() as session:
        try:
            result = EditorialQualityChecksService(session).check_candidate(
                candidate_id,
                dry_run=False,
                prefer_rewrite=prefer_rewrite,
            )
        except (ConfigurationError, InvalidStateTransitionError) as exc:
            error_message = str(exc)
    if error_message:
        _exit_error(error_message)
    if as_json:
        _dump_json(result.model_dump(mode="json"))
    else:
        typer.echo(render_quality_result(result))


@app.command("check-pending")
def check_pending(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha local YYYY-MM-DD sobre published_at"),
    limit: int = typer.Option(20, min=1, help="Maximo de piezas"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza text_draft"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    prefer_rewrite = _prefer_rewrite(use_draft=use_draft, use_rewrite=use_rewrite)
    with session_scope() as session:
        result = EditorialQualityChecksService(session).check_pending(
            reference_date=parsed_date,
            limit=limit,
            dry_run=False,
            prefer_rewrite=prefer_rewrite,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_quality_batch_result(result))


@app.command("dry-run")
def dry_run_checks(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha local YYYY-MM-DD sobre published_at"),
    limit: int = typer.Option(20, min=1, help="Maximo de piezas"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza text_draft"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    prefer_rewrite = _prefer_rewrite(use_draft=use_draft, use_rewrite=use_rewrite)
    with session_scope() as session:
        result = EditorialQualityChecksService(session).check_pending(
            reference_date=parsed_date,
            limit=limit,
            dry_run=True,
            prefer_rewrite=prefer_rewrite,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_quality_batch_result(result))


if __name__ == "__main__":
    app()
