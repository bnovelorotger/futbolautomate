from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import select

from app.db.models import Competition, Match, MatchDataCoverage, MatchEvent, Team
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
    home_score: int = 3,
    away_score: int = 0,
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
        home_score=home_score,
        away_score=away_score,
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
        coverages = {
            row.data_type: row
            for row in session.execute(
                select(MatchDataCoverage).where(MatchDataCoverage.match_id == match.id)
            ).scalars()
        }

        assert result.checked_count == 1
        assert result.enriched_count == 1
        assert result.total_events_found == 3
        assert stored_match is not None
        assert stored_match.has_scorers is True
        assert stored_match.scorer_status == "covered"
        assert stored_match.scorer_checked_at is not None
        assert stored_match.extra_data is not None
        assert stored_match.extra_data["detail_url"] == (
            "https://futbolme.com/resultados-directo/partido/ce-constancia-inter-ibiza-cd/1258230"
        )
        assert stored_match.extra_data["match_events"]["status"] == "complete"
        assert stored_match.extra_data["match_events"]["scorer_status"] == "covered"
        assert stored_match.extra_data["match_events"]["expected_goal_events"] == 3
        assert stored_match.extra_data["match_events"]["stored_events_count"] == 3
        assert stored_match.extra_data["match_events"]["attempt_count"] == 1
        assert len(events) == 3
        assert coverages["scorers"].status == "covered"
        assert coverages["scorers"].expected_count == 3
        assert coverages["scorers"].observed_count == 3
        assert coverages["halftime"].status == "covered"
        assert events[0].team_side == "home"
        assert events[0].minute == 38
        assert events[1].player_raw == "Socias"
        assert events[2].player_raw == "Llabres"
    finally:
        session.close()


def test_match_event_enricher_marks_scoreless_match_without_persisting_events() -> None:
    session = build_session()
    try:
        match = _seed_finished_match(
            session,
            external_id="1259000",
            home_score=0,
            away_score=0,
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
        coverages = {
            row.data_type: row
            for row in session.execute(
                select(MatchDataCoverage).where(MatchDataCoverage.match_id == match.id)
            ).scalars()
        }

        assert row.events_found == 0
        assert stored_match is not None
        assert stored_match.has_scorers is True
        assert stored_match.scorer_status == "no_goals"
        assert row.scorer_status == "no_goals"
        assert stored_match.extra_data is not None
        assert stored_match.extra_data["match_events"]["status"] == "scoreless_complete"
        assert stored_match.extra_data["match_events"]["scorer_status"] == "no_goals"
        assert stored_match.extra_data["match_events"]["expected_goal_events"] == 0
        assert events == []
        assert coverages["scorers"].status == "covered"
        assert coverages["scorers"].expected_count == 0
        assert coverages["scorers"].observed_count == 0
    finally:
        session.close()


def test_match_event_enricher_is_idempotent_when_events_do_not_change() -> None:
    session = build_session()
    try:
        match = _seed_finished_match(session)
        service = MatchEventEnricherService(
            session,
            settings=build_settings(),
            fetch_html=lambda url: read_fixture("futbolme_match_detail_multiple_goals.html"),
        )

        service.enrich_match(match.id)
        session.commit()
        first_ids = [
            event.id
            for event in session.execute(
                select(MatchEvent).where(MatchEvent.match_id == match.id).order_by(MatchEvent.sort_order.asc())
            ).scalars().all()
        ]

        service.enrich_match(match.id)
        session.commit()
        second_events = session.execute(
            select(MatchEvent).where(MatchEvent.match_id == match.id).order_by(MatchEvent.sort_order.asc())
        ).scalars().all()
        stored_match = session.get(Match, match.id)

        assert [event.id for event in second_events] == first_ids
        assert stored_match is not None
        assert stored_match.extra_data["match_events"]["attempt_count"] == 2
        assert stored_match.extra_data["match_events"]["status"] == "complete"
        assert stored_match.scorer_status == "covered"
    finally:
        session.close()


def test_match_event_enricher_leaves_partial_goal_matches_pending_and_applies_retry_cooldown() -> None:
    session = build_session()
    try:
        match = _seed_finished_match(
            session,
            external_id="1259555",
            home_score=3,
            away_score=0,
        )
        service = MatchEventEnricherService(
            session,
            settings=build_settings(),
            fetch_html=lambda url: read_fixture("futbolme_match_detail_goals_home_away.html"),
        )

        first_run = service.enrich_pending(limit=10)
        session.commit()

        stored_match = session.get(Match, match.id)
        stored_events = session.execute(
            select(MatchEvent).where(MatchEvent.match_id == match.id).order_by(MatchEvent.sort_order.asc())
        ).scalars().all()
        scorer_coverage = session.scalar(
            select(MatchDataCoverage).where(
                MatchDataCoverage.match_id == match.id,
                MatchDataCoverage.data_type == "scorers",
            )
        )
        second_run = service.enrich_pending(limit=10)

        assert first_run.checked_count == 1
        assert first_run.rows[0].events_found == 2
        assert first_run.rows[0].has_scorers is False
        assert stored_match is not None
        assert stored_match.has_scorers is False
        assert stored_match.scorer_status == "partial"
        assert first_run.rows[0].scorer_status == "partial"
        assert stored_match.extra_data is not None
        assert stored_match.extra_data["match_events"]["status"] == "partial_retry"
        assert stored_match.extra_data["match_events"]["scorer_status"] == "partial"
        assert stored_match.extra_data["match_events"]["stored_events_count"] == 2
        assert len(stored_events) == 2
        assert scorer_coverage is not None
        assert scorer_coverage.status == "partial"
        assert scorer_coverage.expected_count == 3
        assert scorer_coverage.observed_count == 2
        assert second_run.checked_count == 0
    finally:
        session.close()


def test_match_event_enricher_isolates_failed_match_persistence_and_continues_batch() -> None:
    session = build_session()
    try:
        failed_match = _seed_finished_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="1258230",
        )
        successful_match = _seed_finished_match(
            session,
            competition_code="segunda_rfef_g3_baleares",
            external_id="1258231",
            home_team="UE Porreres",
            away_team="CD Atletico Baleares",
        )
        session.add(
            MatchEvent(
                match_id=failed_match.id,
                team_id=failed_match.home_team_id,
                team_side="home",
                event_type="goal",
                period="Primer Tiempo",
                minute_raw="38",
                minute=38,
                minute_extra=None,
                player_raw="Gerard",
                player_source_url="https://example.com/jugador.php?id=51710",
                sort_order=1,
                source_event_key="Primer Tiempo:home:38:Gerard:https://example.com/jugador.php?id=51710",
                raw_payload={"seeded": True},
            )
        )
        session.commit()

        service = MatchEventEnricherService(
            session,
            settings=build_settings(),
            fetch_html=lambda url: read_fixture("futbolme_match_detail_multiple_goals.html"),
        )
        original_sync = service.repository.sync_for_match
        failed_once = False

        def sync_with_duplicate_failure(match_id: int, payloads: list[dict]):
            nonlocal failed_once
            if match_id == failed_match.id and not failed_once:
                failed_once = True
                service.session.add(
                    MatchEvent(
                        match_id=match_id,
                        team_id=failed_match.home_team_id,
                        team_side="home",
                        event_type="goal",
                        period="Primer Tiempo",
                        minute_raw="38",
                        minute=38,
                        minute_extra=None,
                        player_raw="Gerard",
                        player_source_url="https://example.com/jugador.php?id=51710",
                        sort_order=99,
                        source_event_key="Primer Tiempo:home:38:Gerard:https://example.com/jugador.php?id=51710",
                        raw_payload={"forced": True},
                    )
                )
                service.session.flush()
            return original_sync(match_id, payloads)

        service.repository.sync_for_match = sync_with_duplicate_failure

        result = service.enrich_pending(limit=10)
        session.commit()

        rows_by_match_id = {row.match_id: row for row in result.rows}
        failed_stored_match = session.get(Match, failed_match.id)
        successful_stored_match = session.get(Match, successful_match.id)
        failed_events = session.execute(
            select(MatchEvent).where(MatchEvent.match_id == failed_match.id).order_by(MatchEvent.sort_order.asc())
        ).scalars().all()
        successful_events = session.execute(
            select(MatchEvent).where(MatchEvent.match_id == successful_match.id).order_by(MatchEvent.sort_order.asc())
        ).scalars().all()

        assert result.checked_count == 2
        assert result.enriched_count == 1
        assert rows_by_match_id[failed_match.id].persisted is False
        assert rows_by_match_id[successful_match.id].persisted is True
        assert failed_stored_match is not None
        assert failed_stored_match.has_scorers is False
        assert failed_stored_match.scorer_status == "error"
        assert failed_stored_match.extra_data is not None
        assert failed_stored_match.extra_data["match_events"]["status"] == "error"
        assert failed_stored_match.extra_data["match_events"]["scorer_status"] == "error"
        assert failed_stored_match.extra_data["match_events"]["stored_events_count"] == 1
        assert len(failed_events) == 1
        assert successful_stored_match is not None
        assert successful_stored_match.has_scorers is True
        assert successful_stored_match.scorer_status == "covered"
        assert len(successful_events) == 3
    finally:
        session.close()


ALL_INTEGRATED_COMPETITION_SLUGS = [
    "tercera_rfef_g11",
    "segunda_rfef_g3_baleares",
    "primera_rfef_baleares",
    "division_honor_mallorca",
    "tercera_federacion_femenina_g11",
    "division_honor_ibiza_form",
    "division_honor_menorca",
]


def test_match_event_enricher_processes_all_seven_competition_slugs() -> None:
    """enrich_pending with competition_slug filters correctly for each of the 7 integrated
    competitions.  A match seeded under each slug is picked up and enriched — confirming the
    enricher is not restricted to any subset of competitions."""
    session = build_session()
    try:
        for idx, slug in enumerate(ALL_INTEGRATED_COMPETITION_SLUGS):
            _seed_finished_match(
                session,
                competition_code=slug,
                external_id=f"200000{idx}",
                home_team=f"Home Team {idx}",
                away_team=f"Away Team {idx}",
                home_score=1,
                away_score=0,
            )

        service = MatchEventEnricherService(
            session,
            settings=build_settings(),
            fetch_html=lambda url: read_fixture("futbolme_match_detail_multiple_goals.html"),
        )

        for slug in ALL_INTEGRATED_COMPETITION_SLUGS:
            result = service.enrich_pending(limit=1, competition_slug=slug)
            assert result.checked_count == 1, f"No match picked up for competition slug '{slug}'"
            assert result.enriched_count == 1, f"Match not enriched for competition slug '{slug}'"
    finally:
        session.close()
