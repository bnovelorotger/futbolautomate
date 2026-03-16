from __future__ import annotations

import logging

from app.core.catalog import load_competition_catalog
from app.core.config import get_settings
from app.core.enums import CompetitionIntegrationStatus, RunStatus, SourceName, TargetType
from app.core.exceptions import ConfigurationError
from app.core.logging import configure_logging
from app.db.repositories.scraper_runs import ScraperRunRepository
from app.db.session import init_db, session_scope
from app.schemas.common import ScrapeContext
from app.scrapers.registry import build_scraper
from app.services.ingest_matches import ingest_matches
from app.services.ingest_news import ingest_news
from app.services.ingest_standings import ingest_standings
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


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
                stats = ingest_standings(session, result.records, dry_run=dry_run)
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
        raise ConfigurationError(
            f"La competicion {competition_code} no tiene fuentes automaticas habilitadas"
        )
    return results


def run_daily_pipeline(dry_run: bool = False) -> list[dict]:
    results: list[dict] = []
    competition_catalog = load_competition_catalog()
    for competition in sorted(competition_catalog.values(), key=lambda item: item.priority):
        if competition.status != CompetitionIntegrationStatus.INTEGRATED:
            continue
        for source_name, mapping in competition.sources.items():
            if not mapping.enabled:
                continue
            for target in mapping.urls.keys():
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
