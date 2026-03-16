from __future__ import annotations

import json

import typer

from app.db.session import init_db, session_scope
from app.presenters.system_check import render_editorial_readiness
from app.services.system_check import SystemCheckService

app = typer.Typer(add_completion=False, help="Checks operativos del sistema editorial.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.callback()
def main() -> None:
    """Grupo de comandos de chequeo operativo."""


@app.command("editorial-readiness")
def editorial_readiness(
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        report = SystemCheckService(session).editorial_readiness()
        if as_json:
            _dump_json(report.model_dump(mode="json"))
        else:
            typer.echo(render_editorial_readiness(report))


if __name__ == "__main__":
    app()
