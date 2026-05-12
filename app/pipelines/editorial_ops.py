from __future__ import annotations

import json
import logging
import time
from datetime import date as date_type

import typer

from app.core.run_context import set_run_id
from app.db.repositories.pipeline_metrics import PipelineMetricRepository
from app.db.session import init_db, session_scope
from app.presenters.editorial_ops import render_editorial_ops_preview, render_editorial_ops_run
from app.services.editorial_ops import EditorialOperationsService

logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, help="Operativa diaria del planner editorial.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("preview-day")
def preview_day(
    target_date: str = typer.Option(..., "--date", help="Fecha YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    set_run_id()
    init_db()
    parsed_date = date_type.fromisoformat(target_date)
    t_start = time.time()
    with session_scope() as session:
        result = EditorialOperationsService(session).preview_day(parsed_date)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_editorial_ops_preview(result))
    run_duration = time.time() - t_start
    try:
        with session_scope() as metric_session:
            PipelineMetricRepository(metric_session).upsert(
                parsed_date,
                "editorial_ops_preview_day",
                candidates_generated=result.expected_total,
                run_duration_seconds=run_duration,
                notes=f"total_tasks={result.total_tasks} ready={result.ready_tasks} blocked={result.blocked_tasks}",
            )
    except Exception:
        logger.warning("Failed to record pipeline metric for editorial_ops_preview_day", exc_info=True)


@app.command("run-daily")
def run_daily(
    target_date: str = typer.Option(..., "--date", help="Fecha YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    set_run_id()
    init_db()
    parsed_date = date_type.fromisoformat(target_date)
    t_start = time.time()
    with session_scope() as session:
        result = EditorialOperationsService(session).run_day(parsed_date)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_editorial_ops_run(result))
    run_duration = time.time() - t_start
    try:
        with session_scope() as metric_session:
            PipelineMetricRepository(metric_session).upsert(
                parsed_date,
                "editorial_ops_run_daily",
                candidates_generated=result.generated_total,
                run_duration_seconds=run_duration,
                notes=f"total_tasks={result.total_tasks} inserted={result.inserted_total} updated={result.updated_total} blocked={result.blocked_tasks}",
            )
    except Exception:
        logger.warning("Failed to record pipeline metric for editorial_ops_run_daily", exc_info=True)


if __name__ == "__main__":
    app()
