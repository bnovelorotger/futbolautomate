from __future__ import annotations

import json
from datetime import date as date_type

import typer

from app.db.session import init_db, session_scope
from app.presenters.editorial_ops import render_editorial_ops_preview, render_editorial_ops_run
from app.services.editorial_ops import EditorialOperationsService

app = typer.Typer(add_completion=False, help="Operativa diaria del planner editorial.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("preview-day")
def preview_day(
    target_date: str = typer.Option(..., "--date", help="Fecha YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(target_date)
    with session_scope() as session:
        result = EditorialOperationsService(session).preview_day(parsed_date)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_editorial_ops_preview(result))


@app.command("run-daily")
def run_daily(
    target_date: str = typer.Option(..., "--date", help="Fecha YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(target_date)
    with session_scope() as session:
        result = EditorialOperationsService(session).run_day(parsed_date)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_editorial_ops_run(result))


if __name__ == "__main__":
    app()
