from __future__ import annotations

import json
from datetime import date as date_type

import typer

from app.db.session import init_db, session_scope
from app.services.editorial_phase import EditorialPhaseService

app = typer.Typer(
    add_completion=False,
    help="Diagnostico de fase editorial por competicion.",
    no_args_is_help=True,
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@app.command("report")
def report(
    target_date: str | None = typer.Option(None, "--date", help="Fecha local YYYY-MM-DD"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    parsed_date = date_type.fromisoformat(target_date) if target_date else None
    with session_scope() as session:
        payload = EditorialPhaseService(session).global_phase(parsed_date)
        if as_json:
            _dump_json(payload.model_dump(mode="json"))
            return
        typer.echo(f"fase_global={payload.phase}")
        typer.echo(f"reason={payload.reason}")
        for state in payload.states:
            if not state.has_data:
                continue
            typer.echo(
                " | ".join(
                    [
                        state.competition_slug,
                        str(state.phase),
                        state.reason,
                        f"future={state.future_scheduled_count}",
                        f"finished={state.finished_count}",
                        f"last_finished={state.latest_finished_date or '-'}",
                    ]
                )
            )


if __name__ == "__main__":
    app()
