from __future__ import annotations

import json
import sys

import typer

from app.core.draft_temp import draft_temp_path, load_draft_temp_snapshot, store_draft_temp_snapshot
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
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        snapshot = DraftTempService(session).build_snapshot(
            limit=limit,
            include_rejected=include_rejected,
        )
    path = store_draft_temp_snapshot(snapshot)
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
