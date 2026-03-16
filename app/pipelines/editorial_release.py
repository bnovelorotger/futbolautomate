from __future__ import annotations

import json
from datetime import date as date_type

import typer

from app.db.session import init_db, session_scope
from app.presenters.editorial_release import render_release_result
from app.services.editorial_release_pipeline import EditorialReleasePipelineService

app = typer.Typer(add_completion=False, help="Release automatizado de piezas seguras hasta Typefully.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("dry-run")
def dry_run(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha local YYYY-MM-DD sobre created_at"),
    limit: int = typer.Option(200, min=1, help="Maximo de drafts a evaluar"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza text_draft en autoexport"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text en autoexport"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
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
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_release_result(result))


@app.command("run")
def run(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha local YYYY-MM-DD sobre created_at"),
    limit: int = typer.Option(200, min=1, help="Maximo de drafts a evaluar"),
    use_draft: bool = typer.Option(False, "--use-draft", help="Fuerza text_draft en autoexport"),
    use_rewrite: bool = typer.Option(False, "--use-rewrite", help="Prioriza rewritten_text en autoexport"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    if use_draft and use_rewrite:
        raise typer.BadParameter("No puedes usar --use-draft y --use-rewrite a la vez")
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    prefer_rewrite = False if use_draft else True
    with session_scope() as session:
        result = EditorialReleasePipelineService(session).run(
            reference_date=parsed_date,
            limit=limit,
            dry_run=False,
            prefer_rewrite=prefer_rewrite,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_release_result(result))


if __name__ == "__main__":
    app()
