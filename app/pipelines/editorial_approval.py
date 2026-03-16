from __future__ import annotations

import json
from datetime import date as date_type

import typer

from app.db.session import init_db, session_scope
from app.presenters.editorial_approval import (
    render_approval_result,
    render_approval_status,
)
from app.services.editorial_approval_policy import EditorialApprovalPolicyService

app = typer.Typer(add_completion=False, help="Politica de autoaprobacion para piezas seguras.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("status")
def status(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha local YYYY-MM-DD sobre created_at"),
    limit: int = typer.Option(200, min=1, help="Maximo de drafts a evaluar"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        payload = EditorialApprovalPolicyService(session).status(
            reference_date=parsed_date,
            limit=limit,
        )
        if as_json:
            _dump_json(payload.model_dump(mode="json"))
        else:
            typer.echo(render_approval_status(payload))


@app.command("dry-run")
def dry_run(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha local YYYY-MM-DD sobre created_at"),
    limit: int = typer.Option(200, min=1, help="Maximo de drafts a evaluar"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        payload = EditorialApprovalPolicyService(session).autoapprove(
            reference_date=parsed_date,
            limit=limit,
            dry_run=True,
        )
        if as_json:
            _dump_json(payload.model_dump(mode="json"))
        else:
            typer.echo(render_approval_result(payload))


if __name__ == "__main__":
    app()
