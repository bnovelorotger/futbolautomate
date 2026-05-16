from __future__ import annotations

import json
from pathlib import Path

import typer

from app.channels.typefully.client import TypefullyApiError
from app.channels.typefully.publisher import TypefullyPublisherValidationError
from app.channels.x_browser import auth as x_browser_auth
from app.channels.x_browser.publisher import XBrowserPublishError, XBrowserSessionError
from app.core.config import get_settings
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.session import init_db, session_scope
from app.presenters.x_publication import render_x_result, render_x_rows
from app.services.typefully_publication_service import TypefullyBatchResult, TypefullyPublicationService
from app.services.x_browser_publication_service import XBrowserBatchResult, XBrowserPublicationService

app = typer.Typer(
    add_completion=False,
    help="Publicacion externa en X; browser es la via canonica y los aliases legacy delegan en ella.",
)


def _dump_json(payload) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _exit_error(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


def _warn_legacy_alias(alias: str, canonical: str) -> None:
    typer.echo(
        f"[legacy-alias] '{alias}' delega en '{canonical}' sobre el backend browser de X.",
        err=True,
    )


def _render_typefully_batch(result: TypefullyBatchResult) -> str:
    header = f"dry_run={str(result.dry_run).lower()}\npublished_count={result.published_count}"
    lines = [
        f"{row.id:>3} | {row.competition_slug} | {row.content_type} | priority={row.priority} | "
        f"ref={row.external_publication_ref or '-'} | scheduled={row.scheduled_typefully_date or '-'} | {row.excerpt}"
        for row in result.rows
    ]
    body = "\n".join(lines) if lines else "sin piezas"
    return f"{header}\n{body}"


def _render_browser_batch(result: XBrowserBatchResult) -> str:
    header = (
        f"dry_run={str(result.dry_run).lower()}\n"
        f"published_count={result.published_count}\n"
        f"error_count={result.error_count}"
    )
    lines = [
        f"{row.candidate_id:>3} | {row.competition_slug} | {row.content_type} | "
        f"success={str(row.success).lower()} | ref={row.external_publication_ref or '-'} | "
        f"error={row.error or '-'} | {row.excerpt}"
        for row in result.rows
    ]
    body = "\n".join(lines) if lines else "sin piezas"
    return f"{header}\n{body}"


def _run_browser_pending(
    *,
    limit: int,
    dry_run: bool,
    stagger: int | None,
    as_json: bool,
) -> None:
    import dataclasses

    settings = get_settings()
    effective_stagger = stagger if stagger is not None else settings.x_browser_stagger_seconds
    init_db()
    with session_scope() as session:
        service = XBrowserPublicationService(session)
        result = service.publish_pending(
            limit=limit,
            dry_run=dry_run,
            stagger_seconds=effective_stagger,
        )
        if as_json:
            _dump_json(dataclasses.asdict(result))
        else:
            typer.echo(_render_browser_batch(result))


@app.command("show-pending")
def show_pending(
    limit: int = typer.Option(50, min=1, help="Numero maximo de piezas"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    """Lista piezas pendientes para el backend browser de X."""

    init_db()
    with session_scope() as session:
        rows = XBrowserPublicationService(session).list_pending(limit=limit)
        if as_json:
            _dump_json([row.model_dump(mode="json") for row in rows])
        else:
            typer.echo(render_x_rows(rows))


@app.command("dry-run")
def dry_run_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    """Valida una publicacion individual en X usando el backend browser."""

    init_db()
    with session_scope() as session:
        service = XBrowserPublicationService(session)
        try:
            result = service.publish_candidate(candidate_id, dry_run=True)
        except (
            XBrowserSessionError,
            XBrowserPublishError,
            ConfigurationError,
            InvalidStateTransitionError,
        ) as exc:
            _exit_error(str(exc))
        if as_json:
            _dump_json(result.model_dump(mode="json"))
        else:
            typer.echo(render_x_result(result))


@app.command("publish")
def publish_candidate(
    candidate_id: int = typer.Option(..., "--id", help="ID del content candidate"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    """Publica una pieza individual en X usando el backend browser."""

    init_db()
    error_message: str | None = None
    result = None
    with session_scope() as session:
        service = XBrowserPublicationService(session)
        try:
            result = service.publish_candidate(candidate_id, dry_run=False)
        except (
            XBrowserSessionError,
            XBrowserPublishError,
            ConfigurationError,
            InvalidStateTransitionError,
        ) as exc:
            error_message = str(exc)
    if error_message:
        _exit_error(error_message)
    if result is None:
        _exit_error("No se pudo publicar el candidato")
    if as_json:
        _dump_json(result.model_dump(mode="json"))
    else:
        typer.echo(render_x_result(result))


@app.command("publish-pending")
def publish_pending(
    limit: int = typer.Option(20, min=1, help="Numero maximo de piezas"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No persiste external_publication_ref"),
    stagger: int = typer.Option(None, "--stagger", help="Segundos entre tweets (por defecto: x_browser_stagger_seconds de settings)"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    """Alias legacy de browser-pending; usa el mismo backend browser."""

    _warn_legacy_alias("publish-pending", "browser-pending")
    _run_browser_pending(limit=limit, dry_run=dry_run, stagger=stagger, as_json=as_json)


@app.command("typefully-pending")
def typefully_pending(
    limit: int = typer.Option(50, min=1, help="Numero maximo de piezas"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No persiste external_publication_ref"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    init_db()
    with session_scope() as session:
        service = TypefullyPublicationService(session)
        try:
            result = service.publish_pending(limit=limit, dry_run=dry_run)
        except (TypefullyApiError, TypefullyPublisherValidationError, ConfigurationError, InvalidStateTransitionError) as exc:
            _exit_error(str(exc))
            return
        if as_json:
            import dataclasses

            _dump_json(dataclasses.asdict(result))
        else:
            typer.echo(_render_typefully_batch(result))


@app.command("browser-auth-capture")
def browser_auth_capture() -> None:
    """Abre un navegador para iniciar sesion en X y guarda la sesion en disco."""

    settings = get_settings()
    state_file = Path(settings.x_browser_state_file)
    typer.echo(f"Abriendo navegador. Inicia sesion en X. El archivo de sesion se guardara en: {state_file}")
    x_browser_auth.capture_session(state_file=state_file)
    typer.echo(f"Sesion guardada correctamente en {state_file}")


@app.command("browser-auth-verify")
def browser_auth_verify() -> None:
    """Verifica si la sesion de browser guardada sigue siendo valida."""

    settings = get_settings()
    state_file = Path(settings.x_browser_state_file)
    valid = x_browser_auth.verify_session(state_file=state_file)
    if valid:
        typer.echo("OK - sesion valida")
    else:
        typer.echo("EXPIRED - sesion expirada o no existe. Ejecuta: browser-auth-capture", err=True)
        raise typer.Exit(code=1)


@app.command("browser-pending")
def browser_pending(
    limit: int = typer.Option(20, min=1, help="Numero maximo de piezas"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No persiste external_publication_ref"),
    stagger: int = typer.Option(None, "--stagger", help="Segundos entre tweets (por defecto: x_browser_stagger_seconds de settings)"),
    as_json: bool = typer.Option(False, "--json", help="Salida JSON"),
) -> None:
    """Publica piezas pendientes en X via automatizacion de browser (sin API key)."""

    _run_browser_pending(limit=limit, dry_run=dry_run, stagger=stagger, as_json=as_json)


@app.command("engage-daily")
def engage_daily(
    dry_run: bool = typer.Option(False, "--dry-run", help="Simula los likes sin hacer clic"),
) -> None:
    """Like tweets del timeline para simular actividad humana."""

    from app.services.x_engagement_service import XEngagementService

    try:
        result = XEngagementService().run_daily_engagement(dry_run=dry_run)
    except XBrowserSessionError as exc:
        _exit_error(str(exc))
        return

    if dry_run:
        typer.echo(f"[dry-run] Would like {result.attempted} candidate tweets (daily target: 3)")
    else:
        typer.echo(f"Engagement: liked {result.liked} tweets")


if __name__ == "__main__":
    app()
