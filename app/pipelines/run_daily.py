from __future__ import annotations

import typer

from app.pipelines.runner import run_daily_pipeline

app = typer.Typer(add_completion=False, help="Ejecuta el pipeline diario completo.")


@app.command()
def main(
    dry_run: bool = typer.Option(False, help="No persiste en base de datos"),
) -> None:
    typer.echo(run_daily_pipeline(dry_run=dry_run))


if __name__ == "__main__":
    app()

