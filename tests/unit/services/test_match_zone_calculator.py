from __future__ import annotations

from app.core.standings_zones import CompetitionStandingsZones
from app.schemas.reporting import StandingView
from app.services.match_zone_calculator import MatchZoneCalculator


def _standings() -> list[StandingView]:
    return [
        StandingView(position=1, team="CE Alpha", points=53, played=26, wins=16, draws=5, losses=5, goals_for=44, goals_against=21, goal_difference=23),
        StandingView(position=2, team="CE Beta", points=52, played=26, wins=16, draws=4, losses=6, goals_for=39, goals_against=19, goal_difference=20),
        StandingView(position=3, team="CE Gamma", points=48, played=26, wins=14, draws=6, losses=6, goals_for=37, goals_against=25, goal_difference=12),
        StandingView(position=4, team="CE Delta", points=33, played=26, wins=9, draws=6, losses=11, goals_for=28, goals_against=35, goal_difference=-7),
        StandingView(position=5, team="CE Epsilon", points=31, played=26, wins=8, draws=7, losses=11, goals_for=26, goals_against=33, goal_difference=-7),
        StandingView(position=6, team="CE Golf", points=27, played=26, wins=7, draws=6, losses=13, goals_for=24, goals_against=34, goal_difference=-10),
        StandingView(position=7, team="CE Foxtrot", points=19, played=26, wins=5, draws=4, losses=17, goals_for=18, goals_against=41, goal_difference=-23),
    ]


def _calculator() -> MatchZoneCalculator:
    return MatchZoneCalculator(
        zones={
            "test_comp": CompetitionStandingsZones(
                playoff_positions=[2, 3, 4],
                relegation_positions=[7],
            )
        }
    )


def test_match_zone_calculator_detects_playoff_entry_implication() -> None:
    calculator = _calculator()

    context = calculator.build_team_context("test_comp", _standings(), team_name="CE Epsilon")

    assert context.current.zone == "safe"
    assert context.current.gaps.points_to_playoff == 2
    assert context.current.gaps.margin_above_relegation == 12
    assert context.win_scenario.simulated_position == 4
    assert context.win_scenario.simulated_zone == "playoff"
    assert context.win_scenario.crosses_into == "playoff"
    assert context.win_scenario.implication == "Una victoria lo meteria en playoff"


def test_match_zone_calculator_detects_escape_from_relegation_and_lead_race() -> None:
    calculator = _calculator()

    relegation_context = calculator.build_team_context("test_comp", _standings(), team_name="CE Foxtrot")
    title_context = calculator.build_team_context("test_comp", _standings(), team_name="CE Beta")

    assert relegation_context.current.zone == "relegation"
    assert relegation_context.current.gaps.points_to_safety == 8
    assert relegation_context.win_scenario.simulated_zone == "relegation"
    assert relegation_context.win_scenario.implication is None

    assert title_context.current.zone == "playoff"
    assert title_context.current.gaps.points_to_leader == 1
    assert title_context.win_scenario.simulated_position == 1
    assert title_context.win_scenario.simulated_zone == "leader"
    assert title_context.win_scenario.crosses_into == "leader"
    assert title_context.win_scenario.implication == "Una victoria lo llevaria al liderato"


def test_match_zone_calculator_builds_match_context_for_both_teams() -> None:
    calculator = _calculator()

    context = calculator.build_match_context(
        "test_comp",
        _standings(),
        home_team="CE Delta",
        away_team="CE Epsilon",
    )

    assert context.home_team.team == "CE Delta"
    assert context.away_team.team == "CE Epsilon"
    assert context.home_team.current.zone == "playoff"
    assert context.away_team.current.zone == "safe"
