from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.exceptions import ConfigurationError
from app.db.repositories.competitions import CompetitionRepository
from app.db.repositories.matches import MatchRepository
from app.db.repositories.teams import TeamRepository
from app.normalizers.competitions import CompetitionNormalizer
from app.normalizers.dates import parse_match_datetime
from app.normalizers.statuses import normalize_match_status
from app.normalizers.teams import TeamNameNormalizer
from app.schemas.common import IngestStats
from app.schemas.competition import CompetitionSeed
from app.schemas.match import MatchRecord
from app.services.deduplication import match_content_hash
from app.services.validation import validate_match_record
from app.utils.time import utcnow


def _ensure_competition(session: Session, record: MatchRecord):
    catalog = load_competition_catalog()
    normalizer = CompetitionNormalizer()
    match = normalizer.resolve(record.competition_name, record.competition_code)
    if match is None:
        raise ConfigurationError(
            f"No se pudo resolver la competición para {record.source_url}: {record.competition_name}"
        )
    definition = catalog[match.code]
    payload = CompetitionSeed(
        code=definition.code,
        name=definition.name,
        normalized_name=match.normalized_name,
        category_level=definition.category_level,
        gender=definition.gender,
        region=definition.region,
        country=definition.country,
        federation=definition.federation,
        source_name=str(record.source_name),
        source_competition_id=definition.sources.get(record.source_name).competition_id
        if definition.sources.get(record.source_name)
        else None,
    )
    return CompetitionRepository(session).create_or_update(**payload.model_dump())


def ingest_matches(session: Session, records: list[MatchRecord], dry_run: bool = False) -> IngestStats:
    stats = IngestStats(found=len(records))
    team_normalizer = TeamNameNormalizer()
    competition_normalizer = CompetitionNormalizer()
    team_repo = TeamRepository(session)
    match_repo = MatchRepository(session)

    for record in records:
        record.status = normalize_match_status(record.status_raw)
        validate_match_record(record)
        competition_match = competition_normalizer.resolve(record.competition_name, record.competition_code)
        if competition_match is None:
            raise ConfigurationError(
                f"No se pudo resolver la competición para {record.source_url}: {record.competition_name}"
            )

        home = team_normalizer.normalize(record.home_team)
        away = team_normalizer.normalize(record.away_team)
        normalized_dates = parse_match_datetime(record.match_date_raw, record.match_time_raw)
        if dry_run:
            continue

        competition = _ensure_competition(session, record)
        home_team, _ = team_repo.get_or_create(
            name=home.canonical,
            normalized_name=home.normalized,
            island=None,
            municipality=None,
            gender="unknown",
            source_name=str(record.source_name),
            source_team_id=None,
        )
        away_team, _ = team_repo.get_or_create(
            name=away.canonical,
            normalized_name=away.normalized,
            island=None,
            municipality=None,
            gender="unknown",
            source_name=str(record.source_name),
            source_team_id=None,
        )
        payload = {
            "external_id": record.external_id,
            "source_name": str(record.source_name),
            "source_url": record.source_url,
            "competition_id": competition.id,
            "season": record.season,
            "group_name": record.group_name,
            "round_name": record.round_name,
            "raw_match_date": normalized_dates.raw_date,
            "raw_match_time": normalized_dates.raw_time,
            "match_date": normalized_dates.match_date,
            "match_time": normalized_dates.match_time,
            "kickoff_datetime": normalized_dates.kickoff_datetime,
            "home_team_id": home_team.id,
            "away_team_id": away_team.id,
            "home_team_raw": record.home_team,
            "away_team_raw": record.away_team,
            "home_score": record.home_score,
            "away_score": record.away_score,
            "status": str(record.status),
            "venue": record.venue,
            "has_lineups": record.has_lineups,
            "has_scorers": record.has_scorers,
            "scraped_at": record.scraped_at or utcnow(),
            "content_hash": match_content_hash(record, home.normalized, away.normalized),
            "extra_data": record.raw_payload,
        }
        _, inserted, updated = match_repo.upsert(payload)
        stats.inserted += int(inserted)
        stats.updated += int(updated)
    return stats
