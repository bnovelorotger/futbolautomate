from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.exceptions import ConfigurationError
from app.db.repositories.competitions import CompetitionRepository
from app.db.repositories.standings import StandingRepository
from app.db.repositories.teams import TeamRepository
from app.normalizers.competitions import CompetitionNormalizer
from app.normalizers.teams import TeamNameNormalizer
from app.schemas.common import IngestStats
from app.schemas.competition import CompetitionSeed
from app.schemas.standing import StandingRecord
from app.services.deduplication import standing_content_hash


def _ensure_competition(session: Session, record: StandingRecord):
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


def ingest_standings(
    session: Session,
    records: list[StandingRecord],
    dry_run: bool = False,
) -> IngestStats:
    stats = IngestStats(found=len(records))
    team_normalizer = TeamNameNormalizer()
    competition_normalizer = CompetitionNormalizer()
    team_repo = TeamRepository(session)
    standings_repo = StandingRepository(session)

    for record in records:
        competition_match = competition_normalizer.resolve(record.competition_name, record.competition_code)
        if competition_match is None:
            raise ConfigurationError(
                f"No se pudo resolver la competición para {record.source_url}: {record.competition_name}"
            )
        team = team_normalizer.normalize(record.team_name)
        if dry_run:
            continue
        competition = _ensure_competition(session, record)
        team_row, _ = team_repo.get_or_create(
            name=team.canonical,
            normalized_name=team.normalized,
            island=None,
            municipality=None,
            gender="unknown",
            source_name=str(record.source_name),
            source_team_id=None,
        )
        payload = {
            "source_name": str(record.source_name),
            "source_url": record.source_url,
            "competition_id": competition.id,
            "season": record.season,
            "group_name": record.group_name,
            "position": record.position,
            "team_id": team_row.id,
            "team_raw": record.team_name,
            "played": record.played,
            "wins": record.wins,
            "draws": record.draws,
            "losses": record.losses,
            "goals_for": record.goals_for,
            "goals_against": record.goals_against,
            "goal_difference": record.goal_difference,
            "points": record.points,
            "form_text": record.form_text,
            "scraped_at": record.scraped_at,
            "content_hash": standing_content_hash(record, team.normalized),
            "extra_data": record.raw_payload,
        }
        _, inserted, updated = standings_repo.upsert(payload)
        stats.inserted += int(inserted)
        stats.updated += int(updated)
    return stats
