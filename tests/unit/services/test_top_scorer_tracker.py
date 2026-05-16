from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import select

from app.db.models import Competition, Match, MatchEvent, Team
from app.services.top_scorer_tracker import TopScorerTrackerService
from tests.unit.services.test_editorial_narratives import build_session


def test_top_scorer_tracker_aggregates_goals_by_player_and_team() -> None:
    session = build_session()
    try:
        competition = Competition(
            code="tercera_rfef_g11",
            name="3a RFEF Grupo 11",
            normalized_name="tercera-rfef-g11",
            category_level=4,
            gender="male",
            region="Baleares",
            country="Spain",
            federation="RFEF",
            source_name="futbolme",
            source_competition_id="3047",
        )
        session.add(competition)
        session.flush()

        alpha = Team(name="CE Alpha", normalized_name="ce-alpha", gender="male")
        beta = Team(name="CE Beta", normalized_name="ce-beta", gender="male")
        gamma = Team(name="CE Gamma", normalized_name="ce-gamma", gender="male")
        session.add_all([alpha, beta, gamma])
        session.flush()

        match_one = Match(
            external_id="m1",
            source_name="futbolme",
            source_url="https://example.com/m1",
            competition_id=competition.id,
            season="2025-26",
            group_name="Grupo test",
            round_name="Jornada 25",
            raw_match_date="2026-03-15",
            raw_match_time="18:00",
            match_date=date(2026, 3, 15),
            match_time=time(18, 0),
            kickoff_datetime=datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc),
            home_team_id=alpha.id,
            away_team_id=beta.id,
            home_team_raw="CE Alpha",
            away_team_raw="CE Beta",
            home_score=2,
            away_score=1,
            status="finished",
            venue=None,
            has_lineups=False,
            has_scorers=True,
            scraped_at=datetime(2026, 3, 15, 21, 0, tzinfo=timezone.utc),
            content_hash="m1",
            extra_data={"detail_url": "https://example.com/detail/m1"},
        )
        match_two = Match(
            external_id="m2",
            source_name="futbolme",
            source_url="https://example.com/m2",
            competition_id=competition.id,
            season="2025-26",
            group_name="Grupo test",
            round_name="Jornada 26",
            raw_match_date="2026-03-22",
            raw_match_time="18:00",
            match_date=date(2026, 3, 22),
            match_time=time(18, 0),
            kickoff_datetime=datetime(2026, 3, 22, 18, 0, tzinfo=timezone.utc),
            home_team_id=gamma.id,
            away_team_id=alpha.id,
            home_team_raw="CE Gamma",
            away_team_raw="CE Alpha",
            home_score=0,
            away_score=1,
            status="finished",
            venue=None,
            has_lineups=False,
            has_scorers=True,
            scraped_at=datetime(2026, 3, 22, 21, 0, tzinfo=timezone.utc),
            content_hash="m2",
            extra_data={"detail_url": "https://example.com/detail/m2"},
        )
        session.add_all([match_one, match_two])
        session.flush()

        session.add_all(
            [
                MatchEvent(
                    match_id=match_one.id,
                    team_id=alpha.id,
                    team_side="home",
                    event_type="goal",
                    period="Primer Tiempo",
                    minute_raw="12",
                    minute=12,
                    minute_extra=None,
                    player_raw="Nando",
                    player_source_url="https://example.com/player/nando",
                    sort_order=1,
                    source_event_key="m1-1",
                    raw_payload={},
                ),
                MatchEvent(
                    match_id=match_one.id,
                    team_id=alpha.id,
                    team_side="home",
                    event_type="goal",
                    period="Segundo Tiempo",
                    minute_raw="77",
                    minute=77,
                    minute_extra=None,
                    player_raw="Nando",
                    player_source_url="https://example.com/player/nando",
                    sort_order=2,
                    source_event_key="m1-2",
                    raw_payload={},
                ),
                MatchEvent(
                    match_id=match_two.id,
                    team_id=alpha.id,
                    team_side="away",
                    event_type="goal",
                    period="Segundo Tiempo",
                    minute_raw="88",
                    minute=88,
                    minute_extra=None,
                    player_raw="Nico",
                    player_source_url="https://example.com/player/nico",
                    sort_order=1,
                    source_event_key="m2-1",
                    raw_payload={},
                ),
            ]
        )
        session.commit()

        result = TopScorerTrackerService(session).top_scorers_for_competition("tercera_rfef_g11")

        assert [row.player for row in result.rows[:2]] == ["Nando", "Nico"]
        assert result.scorer_matches_count == 2
        assert result.goal_events_count == 3
        assert result.distinct_scorers_count == 2
        assert result.rows[0].team == "CE Alpha"
        assert result.rows[0].goals == 2
        assert result.rows[0].latest_goal_date == date(2026, 3, 15)
        assert result.rows[1].goals == 1
    finally:
        session.close()


def test_top_scorer_tracker_filters_to_current_season_and_reference_date() -> None:
    session = build_session()
    try:
        competition = Competition(
            code="tercera_rfef_g11",
            name="3a RFEF Grupo 11",
            normalized_name="tercera-rfef-g11",
            category_level=4,
            gender="male",
            region="Baleares",
            country="Spain",
            federation="RFEF",
            source_name="futbolme",
            source_competition_id="3047",
        )
        session.add(competition)
        session.flush()

        alpha = Team(name="CE Alpha", normalized_name="ce-alpha", gender="male")
        beta = Team(name="CE Beta", normalized_name="ce-beta", gender="male")
        session.add_all([alpha, beta])
        session.flush()

        previous_season = Match(
            external_id="m-prev",
            source_name="futbolme",
            source_url="https://example.com/m-prev",
            competition_id=competition.id,
            season="2024-25",
            group_name="Grupo test",
            round_name="Jornada 30",
            raw_match_date="2025-05-10",
            raw_match_time="18:00",
            match_date=date(2025, 5, 10),
            match_time=time(18, 0),
            kickoff_datetime=datetime(2025, 5, 10, 18, 0, tzinfo=timezone.utc),
            home_team_id=alpha.id,
            away_team_id=beta.id,
            home_team_raw="CE Alpha",
            away_team_raw="CE Beta",
            home_score=1,
            away_score=0,
            status="finished",
            venue=None,
            has_lineups=False,
            has_scorers=True,
            scraped_at=datetime(2025, 5, 10, 21, 0, tzinfo=timezone.utc),
            content_hash="m-prev",
            extra_data={},
        )
        current_season = Match(
            external_id="m-current",
            source_name="futbolme",
            source_url="https://example.com/m-current",
            competition_id=competition.id,
            season="2025-26",
            group_name="Grupo test",
            round_name="Jornada 25",
            raw_match_date="2026-03-15",
            raw_match_time="18:00",
            match_date=date(2026, 3, 15),
            match_time=time(18, 0),
            kickoff_datetime=datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc),
            home_team_id=alpha.id,
            away_team_id=beta.id,
            home_team_raw="CE Alpha",
            away_team_raw="CE Beta",
            home_score=2,
            away_score=0,
            status="finished",
            venue=None,
            has_lineups=False,
            has_scorers=True,
            scraped_at=datetime(2026, 3, 15, 21, 0, tzinfo=timezone.utc),
            content_hash="m-current",
            extra_data={},
        )
        future_match = Match(
            external_id="m-future",
            source_name="futbolme",
            source_url="https://example.com/m-future",
            competition_id=competition.id,
            season="2025-26",
            group_name="Grupo test",
            round_name="Jornada 26",
            raw_match_date="2026-03-22",
            raw_match_time="18:00",
            match_date=date(2026, 3, 22),
            match_time=time(18, 0),
            kickoff_datetime=datetime(2026, 3, 22, 18, 0, tzinfo=timezone.utc),
            home_team_id=beta.id,
            away_team_id=alpha.id,
            home_team_raw="CE Beta",
            away_team_raw="CE Alpha",
            home_score=0,
            away_score=2,
            status="finished",
            venue=None,
            has_lineups=False,
            has_scorers=True,
            scraped_at=datetime(2026, 3, 22, 21, 0, tzinfo=timezone.utc),
            content_hash="m-future",
            extra_data={},
        )
        session.add_all([previous_season, current_season, future_match])
        session.flush()

        session.add_all(
            [
                MatchEvent(
                    match_id=previous_season.id,
                    team_id=alpha.id,
                    team_side="home",
                    event_type="goal",
                    period="Primer Tiempo",
                    minute_raw="19",
                    minute=19,
                    minute_extra=None,
                    player_raw="Veterano",
                    player_source_url=None,
                    sort_order=1,
                    source_event_key="prev-1",
                    raw_payload={},
                ),
                MatchEvent(
                    match_id=current_season.id,
                    team_id=alpha.id,
                    team_side="home",
                    event_type="goal",
                    period="Primer Tiempo",
                    minute_raw="10",
                    minute=10,
                    minute_extra=None,
                    player_raw="Actual",
                    player_source_url=None,
                    sort_order=1,
                    source_event_key="current-1",
                    raw_payload={},
                ),
                MatchEvent(
                    match_id=future_match.id,
                    team_id=alpha.id,
                    team_side="away",
                    event_type="goal",
                    period="Segundo Tiempo",
                    minute_raw="82",
                    minute=82,
                    minute_extra=None,
                    player_raw="Actual",
                    player_source_url=None,
                    sort_order=1,
                    source_event_key="future-1",
                    raw_payload={},
                ),
            ]
        )
        session.commit()

        result = TopScorerTrackerService(session).top_scorers_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )

        assert result.season == "2025-26"
        assert result.reference_date == date(2026, 3, 16)
        assert result.scorer_matches_count == 1
        assert result.goal_events_count == 1
        assert result.distinct_scorers_count == 1
        assert [row.player for row in result.rows] == ["Actual"]
        assert result.rows[0].goals == 1
        assert result.rows[0].latest_goal_date == date(2026, 3, 15)
    finally:
        session.close()


def test_top_scorer_tracker_ignores_matches_without_closed_scorer_coverage() -> None:
    session = build_session()
    try:
        competition = Competition(
            code="tercera_rfef_g11",
            name="3a RFEF Grupo 11",
            normalized_name="tercera-rfef-g11-alt",
            category_level=4,
            gender="male",
            region="Baleares",
            country="Spain",
            federation="RFEF",
            source_name="futbolme",
            source_competition_id="3047-alt",
        )
        session.add(competition)
        session.flush()

        alpha = Team(name="CE Alpha", normalized_name="ce-alpha-alt", gender="male")
        beta = Team(name="CE Beta", normalized_name="ce-beta-alt", gender="male")
        session.add_all([alpha, beta])
        session.flush()

        covered_match = Match(
            external_id="m-covered",
            source_name="futbolme",
            source_url="https://example.com/m-covered",
            competition_id=competition.id,
            season="2025-26",
            group_name="Grupo test",
            round_name="Jornada 25",
            raw_match_date="2026-03-15",
            raw_match_time="18:00",
            match_date=date(2026, 3, 15),
            match_time=time(18, 0),
            kickoff_datetime=datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc),
            home_team_id=alpha.id,
            away_team_id=beta.id,
            home_team_raw="CE Alpha",
            away_team_raw="CE Beta",
            home_score=1,
            away_score=0,
            status="finished",
            venue=None,
            has_lineups=False,
            has_scorers=True,
            scraped_at=datetime(2026, 3, 15, 21, 0, tzinfo=timezone.utc),
            content_hash="m-covered",
            extra_data={},
        )
        partial_match = Match(
            external_id="m-partial",
            source_name="futbolme",
            source_url="https://example.com/m-partial",
            competition_id=competition.id,
            season="2025-26",
            group_name="Grupo test",
            round_name="Jornada 26",
            raw_match_date="2026-03-22",
            raw_match_time="18:00",
            match_date=date(2026, 3, 22),
            match_time=time(18, 0),
            kickoff_datetime=datetime(2026, 3, 22, 18, 0, tzinfo=timezone.utc),
            home_team_id=alpha.id,
            away_team_id=beta.id,
            home_team_raw="CE Alpha",
            away_team_raw="CE Beta",
            home_score=3,
            away_score=0,
            status="finished",
            venue=None,
            has_lineups=False,
            has_scorers=False,
            scraped_at=datetime(2026, 3, 22, 21, 0, tzinfo=timezone.utc),
            content_hash="m-partial",
            extra_data={"match_events": {"status": "partial_retry", "expected_goal_events": 3, "events_found": 2}},
        )
        session.add_all([covered_match, partial_match])
        session.flush()

        session.add_all(
            [
                MatchEvent(
                    match_id=covered_match.id,
                    team_id=alpha.id,
                    team_side="home",
                    event_type="goal",
                    period="Primer Tiempo",
                    minute_raw="10",
                    minute=10,
                    minute_extra=None,
                    player_raw="Seguro",
                    player_source_url=None,
                    sort_order=1,
                    source_event_key="covered-1",
                    raw_payload={},
                ),
                MatchEvent(
                    match_id=partial_match.id,
                    team_id=alpha.id,
                    team_side="home",
                    event_type="goal",
                    period="Primer Tiempo",
                    minute_raw="11",
                    minute=11,
                    minute_extra=None,
                    player_raw="Incompleto",
                    player_source_url=None,
                    sort_order=1,
                    source_event_key="partial-1",
                    raw_payload={},
                ),
                MatchEvent(
                    match_id=partial_match.id,
                    team_id=alpha.id,
                    team_side="home",
                    event_type="goal",
                    period="Segundo Tiempo",
                    minute_raw="77",
                    minute=77,
                    minute_extra=None,
                    player_raw="Incompleto",
                    player_source_url=None,
                    sort_order=2,
                    source_event_key="partial-2",
                    raw_payload={},
                ),
            ]
        )
        session.commit()

        result = TopScorerTrackerService(session).top_scorers_for_competition("tercera_rfef_g11")

        assert result.scorer_matches_count == 1
        assert result.goal_events_count == 1
        assert result.distinct_scorers_count == 1
        assert [row.player for row in result.rows] == ["Seguro"]
    finally:
        session.close()
