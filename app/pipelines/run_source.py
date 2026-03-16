from __future__ import annotations

import typer

from app.core.enums import SourceName, TargetType
from app.pipelines import runner

app = typer.Typer(add_completion=False, help="Ejecuta un scraper concreto.")


@app.command()
def main(
    source: SourceName = typer.Option(..., help="Fuente a ejecutar"),
    target: TargetType = typer.Option(..., help="Tipo de dato a extraer"),
    competition: str | None = typer.Option(None, help="Código de competición"),
    dry_run: bool = typer.Option(False, help="No persiste en base de datos"),
    url: str | None = typer.Option(None, help="Override temporal de URL"),
) -> None:
    result = runner.run_source_pipeline(
        source=source,
        target=target,
        competition_code=competition,
        dry_run=dry_run,
        override_url=url,
    )
    typer.echo(result)


if __name__ == "__main__":
    app()
