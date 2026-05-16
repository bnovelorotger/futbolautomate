from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date as date_type

import typer

from app.core.run_context import set_run_id
from app.db.repositories.pipeline_metrics import PipelineMetricRepository
from app.db.session import init_db, session_scope
from app.presenters.editorial_release import render_release_result
from app.services.editorial_release_pipeline import EditorialReleasePipelineService

logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, help="Release automatizado de piezas seguras con exportacion JSON local.")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("dry-run")
def dry_run(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha local YYYY-MM-DD sobre created_at"),
    limit: int = typer.Option(200, min=1, help="Maximo de drafts a evaluar"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza text_draft en la exportacion JSON"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text en la exportacion JSON"),
    publish_x: bool = typer.Option(False, "--publish-x", help="Simula tambien la publicacion en X de las piezas despachadas"),
    publish_typefully: bool = typer.Option(False, "--publish-typefully", help="Simula tambien la publicacion en Typefully de las piezas despachadas"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    set_run_id()
    init_db()
    if use_draft and use_rewrite:
        raise typer.BadParameter("No puedes usar --use-draft y --use-rewrite a la vez")
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    prefer_rewrite = False if use_draft else True
    with session_scope() as session:
        result = EditorialReleasePipelineService(session).run(
            reference_date=parsed_date,
            limit=limit,
            dry_run=True,
            prefer_rewrite=prefer_rewrite,
            publish_to_x=publish_x,
            publish_via_typefully=publish_typefully,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_release_result(result))


@app.command("run")
def run(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha local YYYY-MM-DD sobre created_at"),
    limit: int = typer.Option(200, min=1, help="Maximo de drafts a evaluar"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza text_draft en la exportacion JSON"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text en la exportacion JSON"),
    publish_x: bool = typer.Option(False, "--publish-x", help="Publica tambien en X las piezas despachadas en este run"),
    publish_typefully: bool = typer.Option(False, "--publish-typefully", help="Publica tambien en Typefully las piezas despachadas en este run"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    set_run_id()
    init_db()
    if use_draft and use_rewrite:
        raise typer.BadParameter("No puedes usar --use-draft y --use-rewrite a la vez")
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    prefer_rewrite = False if use_draft else True
    t_start = time.time()
    with session_scope() as session:
        result = EditorialReleasePipelineService(session).run(
            reference_date=parsed_date,
            limit=limit,
            dry_run=False,
            prefer_rewrite=prefer_rewrite,
            publish_to_x=publish_x,
            publish_via_typefully=publish_typefully,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_release_result(result))
    run_duration = time.time() - t_start
    metric_date = parsed_date or date_type.today()
    try:
        with session_scope() as metric_session:
            PipelineMetricRepository(metric_session).upsert(
                metric_date,
                "editorial_release",
                candidates_approved=result.autoapproved_count,
                candidates_published=result.dispatched_count,
                candidates_rejected=result.manual_review_count,
                quality_check_failures=sum(
                    1 for row in result.approval_rows if row.policy_reason == "quality_errors_present"
                ),
                run_duration_seconds=run_duration,
            )
    except Exception:
        logger.warning("Failed to record pipeline metric for editorial_release", exc_info=True)


if __name__ == "__main__":
    app()
