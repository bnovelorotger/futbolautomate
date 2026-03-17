from __future__ import annotations

import json
import sys
from datetime import date as date_type

import typer

from app.core.typefully_autoexport import (
    store_typefully_autoexport_last_run,
)
from app.db.session import init_db, session_scope
from app.presenters.typefully_autoexport import (
    render_typefully_autoexport_candidates,
    render_typefully_autoexport_result,
    render_typefully_autoexport_status,
)
from app.services.typefully_autoexport_service import TypefullyAutoexportService

app = typer.Typer(add_completion=False, help="Autoexportacion controlada de drafts a Typefully.")

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


@app.command("dry-run")
def dry_run_autoexport(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha local YYYY-MM-DD sobre published_at"),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Maximo de piezas a evaluar"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza text_draft"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    prefer_rewrite = _prefer_rewrite(use_draft=use_draft, use_rewrite=use_rewrite)
    with session_scope() as session:
        result = TypefullyAutoexportService(session).run(
            dry_run=True,
            reference_date=parsed_date,
            limit=limit,
            prefer_rewrite=prefer_rewrite,
        )
        store_typefully_autoexport_last_run(result)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_typefully_autoexport_result(result))


@app.command("run")
def run_autoexport(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha local YYYY-MM-DD sobre published_at"),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Maximo de piezas a evaluar"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza text_draft"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    prefer_rewrite = _prefer_rewrite(use_draft=use_draft, use_rewrite=use_rewrite)
    result = None
    error_message: str | None = None
    with session_scope() as session:
        service = TypefullyAutoexportService(session)
        if not service.policy.enabled:
            error_message = "La autoexportacion de Typefully esta desactivada en app/config/typefully_autoexport.json"
        else:
            result = service.run(
                dry_run=False,
                reference_date=parsed_date,
                limit=limit,
                prefer_rewrite=prefer_rewrite,
            )
            store_typefully_autoexport_last_run(result)
    if error_message:
        _exit_error(error_message)
    if as_json:
        _dump_json(result.model_dump(mode="json"))
    else:
        typer.echo(render_typefully_autoexport_result(result))


@app.command("status")
def autoexport_status(
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        status = TypefullyAutoexportService(session).status()
        if as_json:
            _dump_json(status.model_dump(mode="json"))
        else:
            typer.echo(render_typefully_autoexport_status(status))


@app.command("pending-capacity")
def autoexport_pending_capacity(
    limit: int | None = typer.Option(None, "--limit", min=1, help="Maximo de piezas a listar"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza text_draft"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    prefer_rewrite = _prefer_rewrite(use_draft=use_draft, use_rewrite=use_rewrite)
    with session_scope() as session:
        rows = TypefullyAutoexportService(session).list_pending_capacity(
            limit=limit,
            prefer_rewrite=prefer_rewrite,
        )
        payload = {"count": len(rows), "rows": [row.model_dump(mode="json") for row in rows]}
        if as_json:
            _dump_json(payload)
        else:
            typer.echo(render_typefully_autoexport_candidates(rows, title="pending_capacity"))


if __name__ == "__main__":
    app()
