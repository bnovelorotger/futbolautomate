from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import SourceName
from app.core.standings_zones import CompetitionStandingsZones
from app.db.base import Base
from app.db.models import ContentCandidate
from app.schemas.standing import StandingRecord
from app.services.ingest_standings import ingest_standings
from app.services.standings_events import StandingsEventsService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def _rows(order: list[str]) -> list[dict]:
    base_points = 58
    rows: list[dict] = []
    for index, team in enumerate(order, start=1):
        rows.append(
            {
                "position": index,
                "team_name": team,
                "played": 28,
                "wins": max(0, 17 - index),
                "draws": index % 3,
                "losses": index % 4,
                "goals_for": max(12, base_points - index * 2),
                "goals_against": 14 + index,
                "goal_difference": max(12, base_points - index * 2) - (14 + index),
                "points": base_points - index * 2,
            }
        )
    return rows


def ingest_snapshot(
    session: Session,
    *,
    competition_code: str,
    competition_name: str,
    source_url: str,
    timestamp: datetime,
    run_id: int,
    rows: list[dict],
) -> None:
    records = [
        StandingRecord(
            source_name=SourceName.FUTBOLME,
            source_url=source_url,
            competition_code=competition_code,
            competition_name=competition_name,
            season="2025-26",
            group_name="Grupo test",
            position=row["position"],
            team_name=row["team_name"],
            played=row["played"],
            wins=row["wins"],
            draws=row["draws"],
            losses=row["losses"],
            goals_for=row["goals_for"],
            goals_against=row["goals_against"],
            goal_difference=row["goal_difference"],
            points=row["points"],
            scraped_at=timestamp,
        )
        for row in rows
    ]
    ingest_standings(session, records, dry_run=False, scraper_run_id=run_id)
    session.commit()


def test_standings_events_generate_candidates_without_cross_competition_mix() -> None:
    session = build_session()
    try:
        ingest_snapshot(
            session,
            competition_code="tercera_rfef_g11",
            competition_name="3a RFEF Grupo 11",
            source_url="https://example.com/tercera/standings",
            timestamp=datetime(2026, 3, 9, 8, 0, tzinfo=timezone.utc),
            run_id=101,
            rows=_rows(
                [
                    "CE Alpha",
                    "CE Beta",
                    "CE Gamma",
                    "CE Delta",
                    "CE Epsilon",
                    "CE Foxtrot",
                    "CE Gama",
                    "CE Hotel",
                ]
            ),
        )
        ingest_snapshot(
            session,
            competition_code="tercera_rfef_g11",
            competition_name="3a RFEF Grupo 11",
            source_url="https://example.com/tercera/standings",
            timestamp=datetime(2026, 3, 16, 8, 0, tzinfo=timezone.utc),
            run_id=102,
            rows=_rows(
                [
                    "CE Beta",
                    "CE Gamma",
                    "CE Gama",
                    "CE Alpha",
                    "CE Epsilon",
                    "CE Delta",
                    "CE Foxtrot",
                    "CE Hotel",
                ]
            ),
        )
        ingest_snapshot(
            session,
            competition_code="segunda_rfef_g3_baleares",
            competition_name="2a RFEF Grupo 3",
            source_url="https://example.com/segunda/standings",
            timestamp=datetime(2026, 3, 9, 8, 0, tzinfo=timezone.utc),
            run_id=201,
            rows=_rows(
                [
                    "Torrent CF",
                    "UE Porreres",
                    "UD Poblense",
                    "Atletico Baleares",
                ]
            ),
        )
        ingest_snapshot(
            session,
            competition_code="segunda_rfef_g3_baleares",
            competition_name="2a RFEF Grupo 3",
            source_url="https://example.com/segunda/standings",
            timestamp=datetime(2026, 3, 16, 8, 0, tzinfo=timezone.utc),
            run_id=202,
            rows=_rows(
                [
                    "UE Porreres",
                    "Torrent CF",
                    "UD Poblense",
                    "Atletico Baleares",
                ]
            ),
        )

        service = StandingsEventsService(
            session,
            zones={
                "tercera_rfef_g11": CompetitionStandingsZones(
                    playoff_positions=[1, 2, 3, 4],
                    relegation_positions=[7, 8],
                ),
                "segunda_rfef_g3_baleares": CompetitionStandingsZones(
                    playoff_positions=[1, 2],
                    relegation_positions=[4],
                ),
            },
        )

        preview = service.preview_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 16))
        result = service.generate_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 16))
        session.commit()

        rows = session.execute(
            select(ContentCandidate).order_by(ContentCandidate.id.asc())
        ).scalars().all()

        assert preview.rows
        assert result.stats.inserted == len(result.rows)
        assert rows
        assert all(row.competition_slug == "tercera_rfef_g11" for row in rows)
        assert all(row.content_type == "standings_event" for row in rows)
        assert all("Torrent CF" not in row.text_draft and "UE Porreres" not in row.text_draft for row in rows)
    finally:
        session.close()
