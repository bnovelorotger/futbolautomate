from __future__ import annotations

import json

import typer

from app.db.session import init_db, session_scope
from app.presenters.competition_catalog import (
    render_competition_catalog_seed_result,
    render_competition_catalog_status,
)
from app.services.competition_catalog_service import CompetitionCatalogService

app = typer.Typer(add_completion=False, help="Check y seed de competiciones del catalogo tecnico.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("status")
def status(
    integrated_only: bool = typer.Option(False, "--integrated-only", help="Solo competiciones integrated"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        rows = CompetitionCatalogService(session).status(integrated_only=integrated_only)
        if as_json:
            _dump_json([row.model_dump(mode="json") for row in rows])
        else:
            typer.echo(render_competition_catalog_status(rows))


@app.command("seed")
def seed(
    integrated_only: bool = typer.Option(False, "--integrated-only", help="Solo competiciones integrated"),
    missing_only: bool = typer.Option(False, "--missing-only", help="Solo sembrar las que falten en BD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        result = CompetitionCatalogService(session).seed_competitions(
            integrated_only=integrated_only,
            missing_only=missing_only,
        )
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_competition_catalog_seed_result(result))


if __name__ == "__main__":
    app()
