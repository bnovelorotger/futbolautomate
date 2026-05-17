from __future__ import annotations

import logging

import typer

from app.core.catalog import load_competition_catalog
from app.core.config import get_settings
from app.core.enums import CompetitionIntegrationStatus, RunStatus, SourceName, TargetType
from app.core.exceptions import ConfigurationError
from app.core.logging import configure_logging
from app.core.run_context import set_run_id
from app.db.repositories.scraper_runs import ScraperRunRepository
from app.db.session import init_db, session_scope
from app.pipelines.match_events import app as match_events_app
from app.pipelines.pipeline_metrics import app as pipeline_metrics_app
from app.pipelines.pipeline_summary import app as pipeline_summary_app
from app.pipelines.top_scorer import app as top_scorer_app
from app.schemas.common import ScrapeContext
from app.scrapers.registry import build_scraper
from app.services.ingest_matches import ingest_matches
from app.services.ingest_news import ingest_news
from app.services.ingest_standings import ingest_standings
from app.services.telegram_notification_service import TelegramNotificationService
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

app = typer.Typer(
    add_completion=False,
    help="Runner principal del sistema de pipelines de futbol balear.",
    no_args_is_help=True,
)
app.add_typer(match_events_app, name="match_events")
app.add_typer(pipeline_metrics_app, name="pipeline_metrics")
app.add_typer(pipeline_summary_app, name="pipeline_summary")
app.add_typer(top_scorer_app, name="top_scorer")

telegram_app = typer.Typer(
    add_completion=False,
    help="Comandos de configuracion y prueba de notificaciones Telegram.",
    no_args_is_help=True,
)
app.add_typer(telegram_app, name="telegram_notify")


@telegram_app.command("setup")
def telegram_setup() -> None:
    """Descubre el chat_id llamando a getUpdates. Envia un mensaje al bot primero si no aparece ninguno."""
    settings = get_settings()
    svc = TelegramNotificationService(settings=settings)
    updates = svc.get_updates()

    if not updates:
        typer.echo("No se encontraron actualizaciones.")
        typer.echo("Asegurate de haber enviado un mensaje al bot antes de ejecutar este comando.")
        return

    seen: set[str] = set()
    for update in updates:
        chat_id: str | None = None
        if "message" in update and "chat" in update["message"]:
            chat_id = str(update["message"]["chat"]["id"])
        elif "callback_query" in update and "message" in update["callback_query"]:
            chat_id = str(update["callback_query"]["message"]["chat"]["id"])
        if chat_id and chat_id not in seen:
            seen.add(chat_id)
            typer.echo(f"Chat ID encontrado: {chat_id}")

    if not seen:
        typer.echo("No se encontraron chat_ids en las actualizaciones.")
        typer.echo("Asegurate de haber enviado un mensaje al bot antes de ejecutar este comando.")


@telegram_app.command("test")
def telegram_test(
    message: str = typer.Argument(..., help="Mensaje de prueba a enviar"),
) -> None:
    """Envia un mensaje de prueba para verificar la configuracion de Telegram."""
    settings = get_settings()
    svc = TelegramNotificationService(settings=settings)
    success = svc.send_message(message)
    if success:
        typer.echo("Mensaje enviado correctamente.")
    else:
        typer.echo("Error al enviar el mensaje. Comprueba TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.", err=True)
        raise typer.Exit(code=1)


def format_run_summary(
    run_id: int,
    source: SourceName,
    target: TargetType,
    competition_code: str | None,
    stats,
    dry_run: bool,
) -> str:
    competition = competition_code or "-"
    return (
        f"run_id={run_id} source={source} target={target} competition={competition} "
        f"found={stats.found} inserted={stats.inserted} updated={stats.updated} dry_run={dry_run}"
    )


def run_source_pipeline(
    source: SourceName,
    target: TargetType,
    competition_code: str | None = None,
    dry_run: bool = False,
    override_url: str | None = None,
) -> dict:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_db()
    scraper = build_scraper(source)
    context = ScrapeContext(
        source=source,
        target=target,
        competition_code=competition_code,
        dry_run=dry_run,
        override_url=override_url,
    )

    with session_scope() as session:
        runs = ScraperRunRepository(session)
        run = runs.create(
            scraper_name=scraper.__class__.__name__,
            source_name=str(source),
            target_type=str(target),
            competition_code=competition_code,
            started_at=utcnow(),
            status=str(RunStatus.RUNNING),
            records_found=0,
            records_inserted=0,
            records_updated=0,
            errors_count=0,
        )
        try:
            result = scraper.scrape(context)
            if target == TargetType.MATCHES:
                stats = ingest_matches(session, result.records, dry_run=dry_run)
            elif target == TargetType.STANDINGS:
                stats = ingest_standings(
                    session,
                    result.records,
                    dry_run=dry_run,
                    scraper_run_id=run.id if not dry_run else None,
                )
            else:
                stats = ingest_news(session, result.records, dry_run=dry_run)

            runs.update(
                run,
                finished_at=utcnow(),
                status=str(RunStatus.SUCCESS),
                records_found=stats.found,
                records_inserted=stats.inserted,
                records_updated=stats.updated,
                errors_count=stats.errors,
            )
            summary = format_run_summary(run.id, source, target, competition_code, stats, dry_run=dry_run)
            logger.info(summary)
            return {
                "run_id": run.id,
                "source": str(source),
                "target": str(target),
                "competition": competition_code,
                "stats": stats.model_dump(),
                "dry_run": dry_run,
            }
        except Exception as exc:
            runs.update(
                run,
                finished_at=utcnow(),
                status=str(RunStatus.FAILED),
                errors_count=1,
                error_message=str(exc),
            )
            raise


def run_competition_pipeline(
    competition_code: str,
    target: TargetType | None = None,
    dry_run: bool = False,
) -> list[dict]:
    competition = load_competition_catalog()[competition_code]
    results: list[dict] = []
    for source_name, mapping in competition.sources.items():
        if not mapping.enabled:
            continue
        targets = [target] if target else list(mapping.urls.keys())
        for current_target in targets:
            if current_target is None:
                continue
            results.append(
                run_source_pipeline(
                    source=source_name,
                    target=current_target,
                    competition_code=competition_code,
                    dry_run=dry_run,
                )
            )
    if not results:
        raise ConfigurationError(f"La competicion {competition_code} no tiene fuentes automaticas habilitadas")
    return results


def run_daily_pipeline(dry_run: bool = False) -> list[dict]:
    set_run_id()
    results: list[dict] = []
    competition_catalog = load_competition_catalog()
    for competition in sorted(competition_catalog.values(), key=lambda item: item.priority):
        if competition.status != CompetitionIntegrationStatus.INTEGRATED:
            continue
        for source_name, mapping in competition.sources.items():
            if not mapping.enabled:
                continue
            for target in mapping.urls:
                results.append(
                    run_source_pipeline(
                        source=source_name,
                        target=target,
                        competition_code=competition.code,
                        dry_run=dry_run,
                    )
                )
    for source in (SourceName.FFIB, SourceName.DIARIO_MALLORCA, SourceName.ULTIMA_HORA):
        results.append(run_source_pipeline(source=source, target=TargetType.NEWS, dry_run=dry_run))
    return results


if __name__ == "__main__":
    app()
