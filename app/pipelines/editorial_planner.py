from __future__ import annotations

import json
from datetime import date as date_type

import typer

from app.db.session import init_db, session_scope
from app.presenters.editorial_planner import (
    render_campaign_generation_result,
    render_campaign_plan,
    render_week_plan,
)
from app.services.editorial_planner import EditorialPlannerService

app = typer.Typer(
    add_completion=False,
    help="Planificacion editorial semanal desacoplada de la generacion y la publicacion.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main() -> None:
    """CLI del planner editorial semanal."""


@app.command("today")
def show_today(as_json: bool = typer.Option(False, "--json", help="Salida JSON")) -> None:
    init_db()
    with session_scope() as session:
        plan = EditorialPlannerService(session).plan_for_date()
        if as_json:
            _dump_json(plan.model_dump(mode="json"))
        else:
            typer.echo(render_campaign_plan(plan))


@app.command("date")
def show_date(
    target_date: str = typer.Option(..., "--date", help="Fecha YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(target_date)
    with session_scope() as session:
        plan = EditorialPlannerService(session).plan_for_date(parsed_date)
        if as_json:
            _dump_json(plan.model_dump(mode="json"))
        else:
            typer.echo(render_campaign_plan(plan))


@app.command("week")
def show_week(as_json: bool = typer.Option(False, "--json", help="Salida JSON")) -> None:
    init_db()
    with session_scope() as session:
        plan = EditorialPlannerService(session).week_plan()
        if as_json:
            _dump_json(plan.model_dump(mode="json"))
        else:
            typer.echo(render_week_plan(plan))


@app.command("generate-today")
def generate_today(as_json: bool = typer.Option(False, "--json", help="Salida JSON")) -> None:
    init_db()
    with session_scope() as session:
        result = EditorialPlannerService(session).generate_for_date()
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_campaign_generation_result(result))


@app.command("generate-date")
def generate_date(
    target_date: str = typer.Option(..., "--date", help="Fecha YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(target_date)
    with session_scope() as session:
        result = EditorialPlannerService(session).generate_for_date(parsed_date)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_campaign_generation_result(result))


if __name__ == "__main__":
    app()
