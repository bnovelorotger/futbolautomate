from __future__ import annotations

from datetime import date

from app.core.standings_zones import CompetitionStandingsZones
from app.schemas.race_narrative import RaceNarrativeConfig, RaceNarrativeSeasonContext, RaceNarrativeType
from app.schemas.reporting import StandingView
from app.services.race_narrative_generator import RaceNarrativeService


def _standings(rows: list[tuple[int, str, int]]) -> list[StandingView]:
    return [
        StandingView(
            position=position,
            team=team,
            points=points,
            played=27,
            wins=None,
            draws=None,
            losses=None,
            goals_for=None,
            goals_against=None,
            goal_difference=20 - position,
        )
        for position, team, points in rows
    ]


def test_race_narrative_service_detects_title_playoff_relegation_and_alive_math() -> None:
    standings = _standings(
        [
            (1, "CE Alpha", 61),
            (2, "CE Beta", 61),
            (3, "CE Gamma", 59),
            (4, "CE Delta", 54),
            (5, "CE Epsilon", 53),
            (6, "CE Foxtrot", 52),
            (7, "CE Golf", 50),
            (8, "CE Hotel", 40),
            (9, "CE India", 33),
            (10, "CE Juliet", 32),
            (11, "CE Kilo", 31),
            (12, "CE Lima", 30),
        ]
    )
    zones = CompetitionStandingsZones(playoff_positions=[2, 3, 4, 5], relegation_positions=[10, 11, 12])
    service = RaceNarrativeService()

    result = service.preview_for_standings(
        "custom_competition",
        standings,
        competition_name="Liga Test",
        reference_date=date(2026, 5, 16),
        season_context=RaceNarrativeSeasonContext(total_matchdays=29),
        zones=zones,
    )

    by_type = {row.narrative_type: row for row in result.rows}

    assert set(by_type) == {
        RaceNarrativeType.TITLE_RACE,
        RaceNarrativeType.PLAYOFF_RACE,
        RaceNarrativeType.RELEGATION_RACE,
        RaceNarrativeType.ALIVE_MATHEMATICS,
    }
    title_row = by_type[RaceNarrativeType.TITLE_RACE]
    playoff_row = by_type[RaceNarrativeType.PLAYOFF_RACE]
    relegation_row = by_type[RaceNarrativeType.RELEGATION_RACE]
    alive_row = by_type[RaceNarrativeType.ALIVE_MATHEMATICS]

    assert title_row.team_count == 3
    assert title_row.points_span == 2
    assert "pelean por el liderato" in title_row.text_draft

    assert playoff_row.target_position == 5
    assert playoff_row.team_count == 3
    assert playoff_row.source_payload["target_points"] == 53
    assert "ultima plaza de playoff" in playoff_row.text_draft

    assert relegation_row.target_position == 9
    assert relegation_row.team_count == 3
    assert "salir del descenso" in relegation_row.text_draft

    assert alive_row.target_position == 1
    assert alive_row.team_count == 3
    assert alive_row.rounds_remaining == 2
    assert "opciones matematicas de alcanzar el liderato" in alive_row.text_draft


def test_race_narrative_service_respects_threshold_overrides() -> None:
    standings = _standings(
        [
            (1, "CE Alpha", 61),
            (2, "CE Beta", 61),
            (3, "CE Gamma", 59),
            (4, "CE Delta", 54),
            (5, "CE Epsilon", 53),
            (6, "CE Foxtrot", 52),
            (7, "CE Golf", 50),
            (8, "CE Hotel", 40),
            (9, "CE India", 33),
            (10, "CE Juliet", 32),
            (11, "CE Kilo", 31),
            (12, "CE Lima", 30),
        ]
    )
    zones = CompetitionStandingsZones(playoff_positions=[2, 3, 4, 5], relegation_positions=[10, 11, 12])
    service = RaceNarrativeService(
        config=RaceNarrativeConfig(
            title_max_gap_points=1,
            min_playoff_teams=4,
            min_relegation_teams=4,
            playoff_max_gap_points=1,
            relegation_max_gap_points=1,
            alive_math_max_teams=2,
        )
    )

    rows = service.build_rows(
        "custom_competition",
        standings,
        competition_name="Liga Test",
        season_context=RaceNarrativeSeasonContext(total_matchdays=29),
        zones=zones,
    )

    assert [row.narrative_type for row in rows] == [RaceNarrativeType.TITLE_RACE]
    assert rows[0].team_count == 2
    assert "CE Alpha y CE Beta" in rows[0].text_draft


def test_race_narrative_service_skips_alive_math_without_late_season_context() -> None:
    standings = _standings(
        [
            (1, "CE Alpha", 30),
            (2, "CE Beta", 29),
            (3, "CE Gamma", 28),
            (4, "CE Delta", 27),
            (5, "CE Epsilon", 26),
            (6, "CE Foxtrot", 25),
        ]
    )
    zones = CompetitionStandingsZones(playoff_positions=[2, 3, 4], relegation_positions=[])
    service = RaceNarrativeService(
        config=RaceNarrativeConfig(alive_math_max_rounds_remaining=6)
    )

    rows = service.build_rows(
        "custom_competition",
        standings,
        competition_name="Liga Test",
        season_context=RaceNarrativeSeasonContext(total_matchdays=38),
        zones=zones,
    )

    narrative_types = {row.narrative_type for row in rows}
    assert RaceNarrativeType.ALIVE_MATHEMATICS not in narrative_types
