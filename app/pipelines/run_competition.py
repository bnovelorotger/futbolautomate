from __future__ import annotations

import typer

from app.core.enums import TargetType
from app.pipelines.runner import run_competition_pipeline

app = typer.Typer(add_completion=False, help="Ejecuta todos los scrapers de una competición.")


@app.command()
def main(
    competition: str = typer.Option(..., help="Código de competición"),
    target: TargetType | None = typer.Option(None, help="Filtra por target"),
    dry_run: bool = typer.Option(False, help="No persiste en base de datos"),
) -> None:
    typer.echo(run_competition_pipeline(competition_code=competition, target=target, dry_run=dry_run))


if __name__ == "__main__":
    app()

