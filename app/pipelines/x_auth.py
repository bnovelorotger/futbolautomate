from __future__ import annotations

import json

import typer

from app.channels.x.auth import XAuthError
from app.channels.x.client import XApiError
from app.db.session import init_db, session_scope
from app.presenters.x_auth import render_x_authorization_start, render_x_token_status
from app.services.x_auth_service import XAuthService

app = typer.Typer(add_completion=False, help="Flujo OAuth 2.0 PKCE para autorizar publicacion en X.")


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _exit_error(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


@app.command("start-auth")
def start_auth(as_json: bool = typer.Option(False, "--json", help="Salida JSON")) -> None:
    init_db()
    with session_scope() as session:
        service = XAuthService(session)
        try:
            payload = service.start_authorization()
        except (XAuthError, XApiError) as exc:
            _exit_error(str(exc))
        if as_json:
            _dump_json(payload.model_dump(mode="json"))
        else:
            typer.echo(render_x_authorization_start(payload))


@app.command("exchange-code")
def exchange_code(
    code: str | None = typer.Option(None, help="Authorization code recibido en el callback"),
    state: str | None = typer.Option(None, help="State recibido en el callback"),
    callback_url: str | None = typer.Option(
        None,
        "--callback-url",
        help="URL completa del callback con code y state",
    ),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        service = XAuthService(session)
        try:
            payload = service.exchange_code(code=code, state=state, callback_url=callback_url)
        except (XAuthError, XApiError) as exc:
            _exit_error(str(exc))
        if as_json:
            _dump_json(payload.model_dump(mode="json"))
        else:
            typer.echo(render_x_token_status(payload))


@app.command("verify-user-token")
def verify_user_token(as_json: bool = typer.Option(False, "--json", help="Salida JSON")) -> None:
    init_db()
    with session_scope() as session:
        service = XAuthService(session)
        try:
            payload = service.verify_user_token()
        except (XAuthError, XApiError) as exc:
            _exit_error(str(exc))
        if as_json:
            _dump_json(payload.model_dump(mode="json"))
        else:
            typer.echo(render_x_token_status(payload))


if __name__ == "__main__":
    app()
