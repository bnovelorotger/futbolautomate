from __future__ import annotations

import json
import sys
from datetime import date as date_type

import typer

from app.db.session import init_db, session_scope
from app.services.export_base_service import ExportBaseService

app = typer.Typer(add_completion=False, help="Genera el dataset estructurado export_base.json.")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main() -> None:
    """CLI del export oficial export_base."""


@app.command("generate")
def generate(
    target_date: str | None = typer.Option(None, "--date", help="Fecha YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(target_date) if target_date else None
    with session_scope() as session:
        result = ExportBaseService(session).generate_export_file(reference_date=parsed_date, dry_run=False)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(f"scope={result.scope}")
            typer.echo(f"target_date={result.target_date.isoformat()}")
            typer.echo(f"window_start={result.window_start.isoformat()}")
            typer.echo(f"window_end={result.window_end.isoformat()}")
            typer.echo(f"generated_at={result.generated_at.isoformat()}")
            typer.echo(f"total_items={result.total_items}")
            typer.echo(f"path={result.path}")


if __name__ == "__main__":
    app()
