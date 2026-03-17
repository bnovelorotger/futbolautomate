from __future__ import annotations

import json
from datetime import date as date_type

import typer

from app.db.session import init_db, session_scope
from app.presenters.story_importance import (
    render_story_importance_list,
    render_story_importance_score,
)
from app.services.story_importance import StoryImportanceService

app = typer.Typer(
    add_completion=False,
    help="Scoring editorial determinista de story importance.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main() -> None:
    """CLI de story importance."""


@app.command("show")
def show_day(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha YYYY-MM-DD"),
    limit: int = typer.Option(50, "--limit", help="Numero maximo de candidatos"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = StoryImportanceService(session).show_for_date(reference_date=parsed_date, limit=limit)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_story_importance_list("Story Importance", result))


@app.command("top")
def top_day(
    reference_date: str | None = typer.Option(None, "--date", help="Fecha YYYY-MM-DD"),
    limit: int = typer.Option(10, "--limit", help="Numero maximo de historias"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(reference_date) if reference_date else None
    with session_scope() as session:
        result = StoryImportanceService(session).top_for_date(reference_date=parsed_date, limit=limit)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_story_importance_list("Story Importance Top", result))


@app.command("score")
def score_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content_candidate"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        result = StoryImportanceService(session).score_candidate(candidate_id)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_story_importance_score(result))


@app.command("rank-pending")
def rank_pending(
    limit: int = typer.Option(25, "--limit", help="Numero maximo de candidatos"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        result = StoryImportanceService(session).rank_pending(limit=limit)
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_story_importance_list("Story Importance Pending", result))


if __name__ == "__main__":
    app()
