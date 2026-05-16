from __future__ import annotations

from datetime import date, time

from app.services.milestone_detector import (
    MilestoneDetectorConfig,
    MilestoneDetectorService,
    MilestoneType,
)
from tests.unit.services.test_editorial_narratives import build_session, seed_competition


def seed_milestone_data(session) -> None:
    seed_competition(
        session,
        code="tercera_rfef_g11",
        name="3a RFEF Grupo 11",
        teams=["CE Alpha", "CE Beta", "CE Gamma", "CE Delta", "CE Epsilon", "CE Foxtrot"],
        standings_rows=[
            {"position": 1, "team": "CE Epsilon", "played": 10, "wins": 7, "draws": 2, "losses": 1, "goals_for": 31, "goals_against": 12, "goal_difference": 19, "points": 23},
            {"position": 2, "team": "CE Alpha", "played": 10, "wins": 6, "draws": 3, "losses": 1, "goals_for": 24, "goals_against": 9, "goal_difference": 15, "points": 21},
            {"position": 3, "team": "CE Delta", "played": 10, "wins": 5, "draws": 2, "losses": 3, "goals_for": 18, "goals_against": 13, "goal_difference": 5, "points": 17},
            {"position": 4, "team": "CE Gamma", "played": 10, "wins": 4, "draws": 3, "losses": 3, "goals_for": 20, "goals_against": 16, "goal_difference": 4, "points": 15},
            {"position": 5, "team": "CE Beta", "played": 10, "wins": 3, "draws": 2, "losses": 5, "goals_for": 26, "goals_against": 20, "goal_difference": 6, "points": 11},
            {"position": 6, "team": "CE Foxtrot", "played": 10, "wins": 1, "draws": 2, "losses": 7, "goals_for": 10, "goals_against": 28, "goal_difference": -18, "points": 5},
        ],
        match_rows=[
            {"round_name": "Jornada 1", "match_date": date(2026, 1, 10), "match_time": time(16, 0), "home_team": "CE Foxtrot", "away_team": "CE Epsilon", "home_score": 0, "away_score": 2},
            {"round_name": "Jornada 2", "match_date": date(2026, 1, 17), "match_time": time(16, 0), "home_team": "CE Alpha", "away_team": "CE Foxtrot", "home_score": 1, "away_score": 1},
            {"round_name": "Jornada 2", "match_date": date(2026, 1, 17), "match_time": time(18, 0), "home_team": "CE Gamma", "away_team": "CE Beta", "home_score": 2, "away_score": 1},
            {"round_name": "Jornada 3", "match_date": date(2026, 1, 24), "match_time": time(16, 0), "home_team": "CE Delta", "away_team": "CE Foxtrot", "home_score": 1, "away_score": 0},
            {"round_name": "Jornada 4", "match_date": date(2026, 1, 31), "match_time": time(17, 0), "home_team": "CE Gamma", "away_team": "CE Epsilon", "home_score": 1, "away_score": 1},
            {"round_name": "Jornada 5", "match_date": date(2026, 2, 7), "match_time": time(17, 0), "home_team": "CE Beta", "away_team": "CE Gamma", "home_score": 3, "away_score": 1},
            {"round_name": "Jornada 6", "match_date": date(2026, 2, 14), "match_time": time(17, 0), "home_team": "CE Gamma", "away_team": "CE Delta", "home_score": 2, "away_score": 0},
            {"round_name": "Jornada 7", "match_date": date(2026, 2, 21), "match_time": time(17, 0), "home_team": "CE Epsilon", "away_team": "CE Foxtrot", "home_score": 2, "away_score": 2},
            {"round_name": "Jornada 8", "match_date": date(2026, 2, 28), "match_time": time(12, 0), "home_team": "CE Gamma", "away_team": "CE Foxtrot", "home_score": 3, "away_score": 2},
            {"round_name": "Jornada 8", "match_date": date(2026, 2, 28), "match_time": time(18, 0), "home_team": "CE Alpha", "away_team": "CE Delta", "home_score": 0, "away_score": 0},
            {"round_name": "Jornada 9", "match_date": date(2026, 3, 7), "match_time": time(18, 0), "home_team": "CE Beta", "away_team": "CE Alpha", "home_score": 0, "away_score": 2},
            {"round_name": "Jornada 9", "match_date": date(2026, 3, 7), "match_time": time(18, 15), "home_team": "CE Epsilon", "away_team": "CE Gamma", "home_score": 1, "away_score": 1},
            {"round_name": "Jornada 10", "match_date": date(2026, 3, 14), "match_time": time(18, 0), "home_team": "CE Alpha", "away_team": "CE Beta", "home_score": 1, "away_score": 0},
            {"round_name": "Jornada 10", "match_date": date(2026, 3, 14), "match_time": time(18, 15), "home_team": "CE Gamma", "away_team": "CE Delta", "home_score": 0, "away_score": 2},
            {"round_name": "Jornada 10", "match_date": date(2026, 3, 14), "match_time": time(18, 30), "home_team": "CE Epsilon", "away_team": "CE Foxtrot", "home_score": 5, "away_score": 1},
        ],
    )


def test_milestone_detector_builds_structured_milestones_from_existing_data() -> None:
    session = build_session()
    try:
        seed_milestone_data(session)
        service = MilestoneDetectorService(session)

        result = service.preview_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 16))

        by_type = {row.milestone_type: row for row in result.rows}
        assert set(by_type) == {
            MilestoneType.LONGEST_WINLESS_STREAK,
            MilestoneType.LONGEST_CLEAN_SHEET_STREAK,
            MilestoneType.TOP_SCORING_TEAM,
            MilestoneType.FIRST_HOME_DEFEAT,
            MilestoneType.FIRST_SCORELESS_MATCH,
            MilestoneType.ROUND_BIGGEST_WIN,
            MilestoneType.ROUND_GOALS_RECORD,
        }

        winless = by_type[MilestoneType.LONGEST_WINLESS_STREAK]
        assert winless.teams == ["CE Foxtrot"]
        assert winless.metric_value == 6
        assert winless.source_payload["is_active"] is True

        clean_sheet = by_type[MilestoneType.LONGEST_CLEAN_SHEET_STREAK]
        assert clean_sheet.teams == ["CE Alpha"]
        assert clean_sheet.metric_value == 3
        assert clean_sheet.source_payload["goals_for_during_streak"] == 3

        top_scoring = by_type[MilestoneType.TOP_SCORING_TEAM]
        assert top_scoring.teams == ["CE Epsilon"]
        assert top_scoring.metric_value == 31
        assert top_scoring.source_payload["leader_margin"] == 5

        first_home_defeat = by_type[MilestoneType.FIRST_HOME_DEFEAT]
        assert first_home_defeat.teams == ["CE Gamma", "CE Delta"]
        assert first_home_defeat.metric_value == 4
        assert first_home_defeat.source_payload["home_unbeaten_before_loss"] == 4
        assert first_home_defeat.source_payload["scoreline"] == "0-2"

        first_scoreless = by_type[MilestoneType.FIRST_SCORELESS_MATCH]
        assert first_scoreless.teams == ["CE Gamma", "CE Delta"]
        assert first_scoreless.metric_value == 6
        assert first_scoreless.source_payload["scoring_run_matches"] == 6
        assert first_scoreless.source_payload["venue"] == "home"

        biggest_win = by_type[MilestoneType.ROUND_BIGGEST_WIN]
        assert biggest_win.teams == ["CE Epsilon", "CE Foxtrot"]
        assert biggest_win.metric_value == 4
        assert biggest_win.source_payload["scoreline"] == "5-1"

        goals_record = by_type[MilestoneType.ROUND_GOALS_RECORD]
        assert goals_record.metric_value == 9
        assert goals_record.source_payload["match_count"] == 3
        assert goals_record.source_payload["average_goals_per_match"] == 3.0
    finally:
        session.close()


def test_milestone_detector_respects_threshold_overrides() -> None:
    session = build_session()
    try:
        seed_milestone_data(session)
        service = MilestoneDetectorService(
            session,
            config=MilestoneDetectorConfig(
                min_winless_streak=7,
                min_clean_sheet_streak=4,
                min_top_scoring_goals=40,
                min_top_scoring_margin=8,
                min_home_unbeaten_before_loss=5,
                min_scoring_run_before_blank=7,
                min_biggest_win_margin=5,
                min_round_total_goals=10,
            ),
        )

        rows = service.build_milestones("tercera_rfef_g11", reference_date=date(2026, 3, 16))

        assert rows == []
    finally:
        session.close()
