from __future__ import annotations

import json
import logging

import typer

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.repositories.pipeline_metrics import PipelineMetricRepository
from app.db.session import init_db, session_scope

logger = logging.getLogger(__name__)

app = typer.Typer(
    add_completion=False,
    help="Inspeccion de metricas de pipeline editorial.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main() -> None:
    """CLI de metricas de pipeline."""


@app.command("show")
def show(
    days: int = typer.Option(30, "--days", help="Numero de dias hacia atras a consultar"),
    fmt: str = typer.Option("table", "--format", help="Formato de salida: table o json"),
) -> None:
    """Muestra las metricas de pipeline de los ultimos N dias."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_db()

    with session_scope() as session:
        repo = PipelineMetricRepository(session)
        rows = repo.get_recent(days)

    if not rows:
        typer.echo(f"No pipeline metrics found for the last {days} days.")
        raise typer.Exit(0)

    if fmt == "json":
        payload = [
            {
                "date": str(row.run_date),
                "pipeline": row.pipeline_name,
                "generated": row.candidates_generated,
                "approved": row.candidates_approved,
                "published": row.candidates_published,
                "rejected": row.candidates_rejected,
                "quality_fails": row.quality_check_failures,
                "duration_s": row.run_duration_seconds,
            }
            for row in rows
        ]
        _dump_json(payload)
        return

    # Table output with simple f-string padding
    col_date = 10
    col_pipeline = 24
    col_num = 9

    header = (
        f"{'date':<{col_date}} | "
        f"{'pipeline':<{col_pipeline}} | "
        f"{'generated':>{col_num}} | "
        f"{'approved':>{col_num}} | "
        f"{'published':>{col_num}} | "
        f"{'rejected':>{col_num}} | "
        f"{'quality_fails':>{col_num}} | "
        f"{'duration_s':>{col_num}}"
    )
    separator = "-" * len(header)

    typer.echo(separator)
    typer.echo(header)
    typer.echo(separator)

    for row in rows:
        duration = f"{row.run_duration_seconds:.1f}" if row.run_duration_seconds is not None else "-"
        typer.echo(
            f"{str(row.run_date):<{col_date}} | "
            f"{row.pipeline_name:<{col_pipeline}} | "
            f"{row.candidates_generated:>{col_num}} | "
            f"{row.candidates_approved:>{col_num}} | "
            f"{row.candidates_published:>{col_num}} | "
            f"{row.candidates_rejected:>{col_num}} | "
            f"{row.quality_check_failures:>{col_num}} | "
            f"{duration:>{col_num}}"
        )

    typer.echo(separator)


if __name__ == "__main__":
    app()
