from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import select

from app.db.models import Competition, Match, MatchEvent, Team
from app.services.match_event_enricher import MatchEventEnricherService
from tests.helpers import read_fixture
from tests.unit.services.test_editorial_narratives import build_session
from tests.unit.services.service_test_support import build_settings


def _seed_finished_match(
    session,
    *,
    competition_code: str = "tercera_rfef_g11",
    external_id: str = "1258230",
    home_team: str = "CE Constancia",
    away_team: str = "Inter Ibiza CD",
    source_url: str | None = None,
) -> Match:
    competition = Competition(
        code=competition_code,
        name="3a RFEF Grupo 11",
        normalized_name=f"{competition_code}-normalized",
        category_level=4,
        gender="male",
        region="Baleares",
        country="Spain",
        federation="RFEF",
        source_name="futbolme",
        source_competition_id=competition_code,
    )
    session.add(competition)
    session.flush()

    home = Team(name=home_team, normalized_name=f"{competition_code}-{home_team}".lower().replace(" ", "-"), gender="male")
    away = Team(name=away_team, normalized_name=f"{competition_code}-{away_team}".lower().replace(" ", "-"), gender="male")
    session.add_all([home, away])
    session.flush()

    match = Match(
        external_id=external_id,
        source_name="futbolme",
        source_url=source_url or f"https://futbolme.com/resultados-directo/calendario#match-{external_id}",
        competition_id=competition.id,
        season="2025-26",
        group_name="Grupo test",
        round_name="Jornada 25",
        raw_match_date="2026-03-15",
        raw_match_time="18:00",
        match_date=date(2026, 3, 15),
        match_time=time(18, 0),
        kickoff_datetime=datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc),
        home_team_id=home.id,
        away_team_id=away.id,
        home_team_raw=home_team,
        away_team_raw=away_team,
        home_score=3,
        away_score=0,
        status="finished",
        venue=None,
        has_lineups=False,
        has_scorers=False,
        scraped_at=datetime(2026, 3, 15, 21, 0, tzinfo=timezone.utc),
        content_hash=f"{competition_code}-{external_id}",
        extra_data=None,
    )
    session.add(match)
    session.commit()
    return match


def test_match_event_enricher_persists_goal_events_and_marks_match_enriched() -> None:
    session = build_session()
    try:
        match = _seed_finished_match(session)
        service = MatchEventEnricherService(
            session,
            settings=build_settings(),
            fetch_html=lambda url: read_fixture("futbolme_match_detail_multiple_goals.html"),
        )

        result = service.enrich_pending(limit=10)
        session.commit()

        stored_match = session.get(Match, match.id)
        events = session.execute(
            select(MatchEvent).where(MatchEvent.match_id == match.id).order_by(MatchEvent.sort_order.asc())
        ).scalars().all()

        assert result.checked_count == 1
        assert result.enriched_count == 1
        assert result.total_events_found == 3
        assert stored_match is not None
        assert stored_match.has_scorers is True
        assert stored_match.extra_data is not None
        assert stored_match.extra_data["detail_url"] == (
            "https://futbolme.com/resultados-directo/partido/ce-constancia-inter-ibiza-cd/1258230"
        )
        assert len(events) == 3
        assert events[0].team_side == "home"
        assert events[0].minute == 38
        assert events[1].player_raw == "Socias"
        assert events[2].player_raw == "Llabres"
    finally:
        session.close()


def test_match_event_enricher_marks_scoreless_match_without_persisting_events() -> None:
    session = build_session()
    try:
        match = _seed_finished_match(session, external_id="1259000", home_score=0 if False else 3)
        session.execute(
            select(Match).where(Match.id == match.id)
        )
        service = MatchEventEnricherService(
            session,
            settings=build_settings(),
            fetch_html=lambda url: read_fixture("futbolme_match_detail_nil_nil.html"),
        )

        row = service.enrich_match(match.id)
        session.commit()

        stored_match = session.get(Match, match.id)
        events = session.execute(select(MatchEvent).where(MatchEvent.match_id == match.id)).scalars().all()

        assert row.events_found == 0
        assert stored_match is not None
        assert stored_match.has_scorers is True
        assert events == []
    finally:
        session.close()
