from __future__ import annotations

from datetime import date, time

from app.core.standings_zones import CompetitionStandingsZones
from app.schemas.match_impact import MatchImpactCandidatePayload, MatchImpactScenario
from app.services.match_impact_calculator import MatchImpactCalculatorService
from tests.unit.services.test_editorial_narratives import build_session, seed_competition
from tests.unit.services.test_match_importance import add_scheduled_match


def seed_match_impact_data(session) -> None:
    seed_competition(
        session,
        code="tercera_rfef_g11",
        name="3a RFEF Grupo 11",
        teams=["CE Alpha", "CE Beta", "CE Gamma", "CE Delta", "CE Epsilon", "CE Foxtrot"],
        standings_rows=[
            {"position": 1, "team": "CE Alpha", "played": 20, "wins": 10, "draws": 3, "losses": 7, "goals_for": 28, "goals_against": 18, "goal_difference": 10, "points": 33},
            {"position": 2, "team": "CE Beta", "played": 20, "wins": 8, "draws": 4, "losses": 8, "goals_for": 23, "goals_against": 17, "goal_difference": 6, "points": 28},
            {"position": 3, "team": "CE Gamma", "played": 20, "wins": 7, "draws": 5, "losses": 8, "goals_for": 20, "goals_against": 16, "goal_difference": 4, "points": 26},
            {"position": 4, "team": "CE Delta", "played": 20, "wins": 7, "draws": 4, "losses": 9, "goals_for": 19, "goals_against": 16, "goal_difference": 3, "points": 25},
            {"position": 5, "team": "CE Epsilon", "played": 20, "wins": 7, "draws": 4, "losses": 9, "goals_for": 18, "goals_against": 16, "goal_difference": 2, "points": 25},
            {"position": 6, "team": "CE Foxtrot", "played": 20, "wins": 6, "draws": 4, "losses": 10, "goals_for": 17, "goals_against": 20, "goal_difference": -3, "points": 22},
        ],
        match_rows=[],
    )
    add_scheduled_match(
        session,
        competition_code="tercera_rfef_g11",
        external_id="epsilon-gamma",
        match_date=date(2026, 3, 21),
        match_time=time(18, 0),
        home_team="CE Epsilon",
        away_team="CE Gamma",
    )
    add_scheduled_match(
        session,
        competition_code="tercera_rfef_g11",
        external_id="alpha-beta",
        match_date=date(2026, 3, 21),
        match_time=time(20, 0),
        home_team="CE Alpha",
        away_team="CE Beta",
    )


def test_match_impact_analyze_match_detects_playoff_crossings() -> None:
    session = build_session()
    try:
        seed_match_impact_data(session)
        service = MatchImpactCalculatorService(
            session,
            zones={
                "tercera_rfef_g11": CompetitionStandingsZones(
                    playoff_positions=[2, 3],
                    relegation_positions=[5, 6],
                )
            },
        )
        match = service.queries.editorial_upcoming_matches(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )[0]

        result = service.analyze_match("tercera_rfef_g11", match)

        home_win = next(item for item in result.scenarios if item.scenario == MatchImpactScenario.HOME_WIN)
        assert result.home_team_state.current_position == 5
        assert result.away_team_state.current_position == 3
        assert home_win.crossing_count == 4
        assert [crossing.event_type for crossing in home_win.zone_crossings] == [
            "entered_playoff",
            "left_playoff",
            "left_relegation",
            "entered_relegation",
        ]
        assert [crossing.team for crossing in home_win.zone_crossings] == [
            "CE Epsilon",
            "CE Gamma",
            "CE Epsilon",
            "CE Delta",
        ]
        assert home_win.home_team.projected_position == 3
        assert home_win.home_team.projected_zone_tags == ["playoff"]
        assert home_win.away_team.projected_position == 4
        assert home_win.away_team.projected_zone_tags == []
    finally:
        session.close()


def test_match_impact_preview_prioritizes_highest_zone_swing_match() -> None:
    session = build_session()
    try:
        seed_match_impact_data(session)
        service = MatchImpactCalculatorService(
            session,
            zones={
                "tercera_rfef_g11": CompetitionStandingsZones(
                    playoff_positions=[2, 3],
                    relegation_positions=[5, 6],
                )
            },
        )

        result = service.preview_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )

        assert [row.home_team for row in result.rows] == ["CE Epsilon", "CE Alpha"]
        assert result.rows[0].max_zone_crossings == 4
        assert result.rows[1].max_zone_crossings == 0
    finally:
        session.close()


def test_match_impact_preview_counts_crossings_for_displaced_third_team() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="segunda_rfef_g3_baleares",
            name="2a RFEF Grupo 3",
            teams=["UE Alpha", "UE Beta", "UE Gamma", "UE Delta", "UE Epsilon", "UE Foxtrot"],
            standings_rows=[
                {"position": 1, "team": "UE Alpha", "played": 20, "wins": 10, "draws": 3, "losses": 7, "goals_for": 30, "goals_against": 16, "goal_difference": 14, "points": 33},
                {"position": 2, "team": "UE Beta", "played": 20, "wins": 8, "draws": 4, "losses": 8, "goals_for": 25, "goals_against": 18, "goal_difference": 7, "points": 28},
                {"position": 3, "team": "UE Gamma", "played": 20, "wins": 7, "draws": 5, "losses": 8, "goals_for": 21, "goals_against": 18, "goal_difference": 3, "points": 26},
                {"position": 4, "team": "UE Delta", "played": 20, "wins": 7, "draws": 4, "losses": 9, "goals_for": 20, "goals_against": 18, "goal_difference": 2, "points": 25},
                {"position": 5, "team": "UE Epsilon", "played": 20, "wins": 6, "draws": 4, "losses": 10, "goals_for": 18, "goals_against": 20, "goal_difference": -2, "points": 22},
                {"position": 6, "team": "UE Foxtrot", "played": 20, "wins": 5, "draws": 5, "losses": 10, "goals_for": 16, "goals_against": 22, "goal_difference": -6, "points": 20},
            ],
            match_rows=[],
        )
        add_scheduled_match(
            session,
            competition_code="segunda_rfef_g3_baleares",
            external_id="delta-foxtrot",
            match_date=date(2026, 3, 21),
            match_time=time(18, 0),
            home_team="UE Delta",
            away_team="UE Foxtrot",
        )
        service = MatchImpactCalculatorService(
            session,
            zones={
                "segunda_rfef_g3_baleares": CompetitionStandingsZones(
                    playoff_positions=[2, 3],
                    relegation_positions=[5, 6],
                )
            },
        )
        match = service.queries.editorial_upcoming_matches(
            "segunda_rfef_g3_baleares",
            reference_date=date(2026, 3, 16),
        )[0]

        result = service.analyze_match("segunda_rfef_g3_baleares", match)
        home_win = next(item for item in result.scenarios if item.scenario == MatchImpactScenario.HOME_WIN)

        assert ("UE Delta", "entered_playoff") in {
            (crossing.team, crossing.event_type) for crossing in home_win.zone_crossings
        }
        assert ("UE Gamma", "left_playoff") in {
            (crossing.team, crossing.event_type) for crossing in home_win.zone_crossings
        }
    finally:
        session.close()


def test_match_impact_candidate_payload_defaults_to_future_content_type() -> None:
    payload = MatchImpactCandidatePayload(
        competition_slug="tercera_rfef_g11",
        round_name="Jornada 27",
        match_date=date(2026, 3, 21),
        source_url="https://example.com/match",
        home_team="CE Epsilon",
        away_team="CE Gamma",
        home_team_state={"team": "CE Epsilon", "current_position": 5, "current_points": 25},
        away_team_state={"team": "CE Gamma", "current_position": 3, "current_points": 26},
        max_zone_crossings=2,
        total_zone_crossings=2,
        impact_score=202,
    )

    assert payload.content_type == "match_impact_scenario"
