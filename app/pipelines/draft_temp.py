from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from app.core.config import get_settings
from app.core.draft_temp import draft_temp_path, load_draft_temp_snapshot, store_draft_temp_snapshot
from app.core.logging import configure_logging
from app.core.run_context import set_run_id
from app.db.session import init_db, session_scope
from app.presenters.draft_temp import render_draft_temp_sync
from app.services.draft_temp_service import DraftTempService

app = typer.Typer(add_completion=False, help="Snapshot local JSON de drafts operativos.")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("sync")
def sync_snapshot(
    limit: int = typer.Option(200, min=1, help="Maximo de filas a incluir en el snapshot"),
    include_rejected: bool = typer.Option(False, "--include-rejected", help="Incluye candidatos rechazados"),
    phase3_only: bool = typer.Option(False, "--phase3-only", help="Limita el snapshot al rollout de fase 3"),
    recompute_quality_checks: bool = typer.Option(
        False,
        "--recompute-quality-checks",
        help="Recalcula quality checks en dry-run para el snapshot",
    ),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza text_draft al recalcular checks"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text al recalcular checks"),
    output: Path | None = typer.Option(None, "--output", help="Ruta alternativa para guardar el snapshot"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    set_run_id()
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    if use_draft and use_rewrite:
        raise typer.BadParameter("No puedes usar --use-draft y --use-rewrite a la vez")
    init_db()
    with session_scope() as session:
        snapshot = DraftTempService(session).build_snapshot(
            limit=limit,
            include_rejected=include_rejected,
            phase3_only=phase3_only,
            recompute_quality_checks=recompute_quality_checks,
            prefer_rewrite=not use_draft,
        )
    path = store_draft_temp_snapshot(snapshot, path=output)
    payload = {
        "path": str(path),
        "snapshot": snapshot.model_dump(mode="json"),
    }
    if as_json:
        _dump_json(payload)
    else:
        typer.echo(render_draft_temp_sync(snapshot, path=path))


@app.command("show")
def show_snapshot(as_json: bool = typer.Option(False, "--json", help="Salida JSON")) -> None:
    set_run_id()
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    snapshot = load_draft_temp_snapshot()
    if snapshot is None:
        typer.echo("No existe logs/draft_temp.json", err=True)
        raise typer.Exit(code=1)
    if as_json:
        _dump_json(snapshot.model_dump(mode="json"))
    else:
        typer.echo(render_draft_temp_sync(snapshot, path=draft_temp_path()))


if __name__ == "__main__":
    app()
