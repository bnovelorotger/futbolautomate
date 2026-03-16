from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import MatchStatus, SourceName
from app.db.base import Base
from app.db.models import Match, Standing, StandingSnapshot
from app.schemas.match import MatchRecord
from app.schemas.standing import StandingRecord
from app.services.ingest_matches import ingest_matches
from app.services.ingest_standings import ingest_standings
from app.utils.time import utcnow


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def test_ingest_matches_is_idempotent_and_updates_content() -> None:
    session = build_session()
    try:
        first = MatchRecord(
            source_name=SourceName.FUTBOLME,
            source_url="https://example.com/match/1",
            competition_code="tercera_rfef_g11",
            home_team="At. Baleares",
            away_team="CE Andratx",
            home_score=1,
            away_score=0,
            status=MatchStatus.FINISHED,
            status_raw="Finalizado",
            match_date_raw="14/03/2026",
            match_time_raw="12:00",
            scraped_at=utcnow(),
        )

        stats_1 = ingest_matches(session, [first], dry_run=False)
        session.commit()
        assert stats_1.inserted == 1
        assert stats_1.updated == 0

        stats_2 = ingest_matches(session, [first], dry_run=False)
        session.commit()
        assert stats_2.inserted == 0
        assert stats_2.updated == 0

        changed = first.model_copy(update={"home_score": 2})
        stats_3 = ingest_matches(session, [changed], dry_run=False)
        session.commit()
        assert stats_3.inserted == 0
        assert stats_3.updated == 1

        matches = session.scalars(select(Match)).all()
        assert len(matches) == 1
        assert matches[0].home_score == 2
    finally:
        session.close()


def test_ingest_standings_updates_existing_row_when_team_name_parsing_improves() -> None:
    session = build_session()
    try:
        first = StandingRecord(
            source_name=SourceName.FUTBOLME,
            source_url="https://example.com/standings",
            competition_code="tercera_rfef_g11",
            competition_name="3a RFEF Grupo 11",
            season="2025-26",
            position=1,
            team_name="Mallorca B RCD Mallorca B",
            points=63,
            played=25,
            wins=20,
            draws=3,
            losses=2,
            goals_for=73,
            goals_against=16,
            goal_difference=57,
            scraped_at=utcnow(),
        )

        improved = first.model_copy(update={"team_name": "RCD Mallorca B"})

        stats_1 = ingest_standings(session, [first], dry_run=False)
        session.commit()
        stats_2 = ingest_standings(session, [improved], dry_run=False)
        session.commit()

        standings = session.scalars(select(Standing)).all()
        assert stats_1.inserted == 1
        assert stats_2.inserted == 0
        assert stats_2.updated == 1
        assert len(standings) == 1
        assert standings[0].team_raw == "RCD Mallorca B"
    finally:
        session.close()


def test_ingest_standings_persists_historical_snapshots_without_overwriting_previous_runs() -> None:
    session = build_session()
    try:
        first_scraped_at = utcnow()
        second_scraped_at = first_scraped_at.replace(hour=(first_scraped_at.hour + 1) % 24)
        first = StandingRecord(
            source_name=SourceName.FUTBOLME,
            source_url="https://example.com/standings",
            competition_code="tercera_rfef_g11",
            competition_name="3a RFEF Grupo 11",
            season="2025-26",
            position=1,
            team_name="RCD Mallorca B",
            points=63,
            played=25,
            wins=20,
            draws=3,
            losses=2,
            goals_for=73,
            goals_against=16,
            goal_difference=57,
            scraped_at=first_scraped_at,
        )
        second = first.model_copy(
            update={
                "points": 66,
                "played": 26,
                "wins": 21,
                "goals_for": 75,
                "goal_difference": 59,
                "scraped_at": second_scraped_at,
            }
        )

        ingest_standings(session, [first], dry_run=False, scraper_run_id=11)
        session.commit()
        ingest_standings(session, [second], dry_run=False, scraper_run_id=12)
        session.commit()

        snapshots = session.scalars(
            select(StandingSnapshot).order_by(StandingSnapshot.snapshot_timestamp.asc())
        ).all()
        assert len(snapshots) == 2
        assert snapshots[0].scraper_run_id == 11
        assert snapshots[0].points == 63
        assert snapshots[1].scraper_run_id == 12
        assert snapshots[1].points == 66
        assert snapshots[0].snapshot_timestamp < snapshots[1].snapshot_timestamp
    finally:
        session.close()


def test_ingest_standings_snapshots_do_not_mix_competitions() -> None:
    session = build_session()
    try:
        first = StandingRecord(
            source_name=SourceName.FUTBOLME,
            source_url="https://example.com/tercera/standings",
            competition_code="tercera_rfef_g11",
            competition_name="3a RFEF Grupo 11",
            season="2025-26",
            position=1,
            team_name="RCD Mallorca B",
            points=63,
            scraped_at=utcnow(),
        )
        second = StandingRecord(
            source_name=SourceName.FUTBOLME,
            source_url="https://example.com/segunda/standings",
            competition_code="segunda_rfef_g3_baleares",
            competition_name="2a RFEF Grupo 3",
            season="2025-26",
            position=1,
            team_name="UE Sant Andreu",
            points=54,
            scraped_at=utcnow(),
        )

        ingest_standings(session, [first, second], dry_run=False, scraper_run_id=21)
        session.commit()

        snapshots = session.scalars(select(StandingSnapshot).order_by(StandingSnapshot.id.asc())).all()
        assert len(snapshots) == 2
        assert {snapshot.source_url for snapshot in snapshots} == {
            "https://example.com/tercera/standings",
            "https://example.com/segunda/standings",
        }
        assert snapshots[0].competition_id != snapshots[1].competition_id
    finally:
        session.close()


def test_ingest_standings_uses_single_snapshot_timestamp_per_run() -> None:
    session = build_session()
    try:
        first_scraped_at = utcnow()
        second_scraped_at = first_scraped_at.replace(microsecond=min(first_scraped_at.microsecond + 500, 999999))
        rows = [
            StandingRecord(
                source_name=SourceName.FUTBOLME,
                source_url="https://example.com/tercera/standings",
                competition_code="tercera_rfef_g11",
                competition_name="3a RFEF Grupo 11",
                season="2025-26",
                position=1,
                team_name="RCD Mallorca B",
                points=63,
                scraped_at=first_scraped_at,
            ),
            StandingRecord(
                source_name=SourceName.FUTBOLME,
                source_url="https://example.com/tercera/standings",
                competition_code="tercera_rfef_g11",
                competition_name="3a RFEF Grupo 11",
                season="2025-26",
                position=2,
                team_name="CE Mercadal",
                points=58,
                scraped_at=second_scraped_at,
            ),
        ]

        ingest_standings(session, rows, dry_run=False, scraper_run_id=99)
        session.commit()

        snapshots = session.scalars(
            select(StandingSnapshot).order_by(StandingSnapshot.position.asc())
        ).all()
        expected_timestamp = second_scraped_at.replace(tzinfo=None)
        assert len(snapshots) == 2
        assert {snapshot.snapshot_timestamp for snapshot in snapshots} == {expected_timestamp}
        assert {snapshot.snapshot_date for snapshot in snapshots} == {second_scraped_at.date()}
    finally:
        session.close()
