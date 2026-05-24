from __future__ import annotations

from datetime import date, time

from app.core.enums import ContentType
from app.services.season_wrap_editorial import SeasonWrapEditorialService
from tests.unit.services.test_editorial_narratives import build_session, seed_competition


def test_season_wrap_stats_builds_global_balance_from_finished_matches_and_table() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="primera_rfef_baleares",
            name="Primera RFEF Baleares",
            teams=["UD Ibiza", "CE Europa", "CE Sabadell"],
            standings_rows=[
                {
                    "position": 1,
                    "team": "UD Ibiza",
                    "played": 2,
                    "wins": 2,
                    "draws": 0,
                    "losses": 0,
                    "goals_for": 5,
                    "goals_against": 1,
                    "goal_difference": 4,
                    "points": 6,
                },
                {
                    "position": 2,
                    "team": "CE Europa",
                    "played": 2,
                    "wins": 1,
                    "draws": 0,
                    "losses": 1,
                    "goals_for": 3,
                    "goals_against": 3,
                    "goal_difference": 0,
                    "points": 3,
                },
                {
                    "position": 20,
                    "team": "CE Sabadell",
                    "played": 2,
                    "wins": 0,
                    "draws": 0,
                    "losses": 2,
                    "goals_for": 1,
                    "goals_against": 5,
                    "goal_difference": -4,
                    "points": 0,
                },
            ],
            match_rows=[
                {
                    "round_name": "Jornada 2",
                    "match_date": date(2026, 5, 22),
                    "match_time": time(20, 0),
                    "home_team": "UD Ibiza",
                    "away_team": "CE Europa",
                    "home_score": 3,
                    "away_score": 1,
                },
                {
                    "round_name": "Jornada 1",
                    "match_date": date(2026, 5, 15),
                    "match_time": time(20, 0),
                    "home_team": "CE Sabadell",
                    "away_team": "UD Ibiza",
                    "home_score": 0,
                    "away_score": 2,
                },
            ],
        )

        candidates = SeasonWrapEditorialService(session).build_stats_drafts(
            "primera_rfef_baleares",
            reference_date=date(2026, 5, 24),
        )

        assert len(candidates) == 1
        candidate = candidates[0]
        source_payload = candidate.payload_json["source_payload"]
        assert candidate.content_type == ContentType.SEASON_WRAP_STATS
        assert source_payload["finished_matches_count"] == 2
        assert source_payload["total_goals"] == 6
        assert source_payload["best_attack"]["team"] == "UD Ibiza"
        assert "Balance final" in candidate.text_draft
    finally:
        session.close()


def test_season_wrap_outcomes_lists_champion_and_relegation_zone() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="primera_rfef_baleares",
            name="Primera RFEF Baleares",
            teams=["UD Ibiza", "CE Europa", "CE Sabadell"],
            standings_rows=[
                {
                    "position": 1,
                    "team": "UD Ibiza",
                    "played": 38,
                    "wins": 22,
                    "draws": 8,
                    "losses": 8,
                    "goals_for": 60,
                    "goals_against": 31,
                    "goal_difference": 29,
                    "points": 74,
                },
                {
                    "position": 2,
                    "team": "CE Europa",
                    "played": 38,
                    "wins": 20,
                    "draws": 9,
                    "losses": 9,
                    "goals_for": 55,
                    "goals_against": 33,
                    "goal_difference": 22,
                    "points": 69,
                },
                {
                    "position": 20,
                    "team": "CE Sabadell",
                    "played": 38,
                    "wins": 7,
                    "draws": 8,
                    "losses": 23,
                    "goals_for": 30,
                    "goals_against": 64,
                    "goal_difference": -34,
                    "points": 29,
                },
            ],
            match_rows=[
                {
                    "round_name": "Jornada 38",
                    "match_date": date(2026, 5, 22),
                    "match_time": time(20, 0),
                    "home_team": "UD Ibiza",
                    "away_team": "CE Europa",
                    "home_score": 2,
                    "away_score": 0,
                }
            ],
        )

        candidates = SeasonWrapEditorialService(session).build_outcome_drafts(
            "primera_rfef_baleares",
            reference_date=date(2026, 5, 24),
        )

        assert len(candidates) == 1
        source_payload = candidates[0].payload_json["source_payload"]
        assert candidates[0].content_type == ContentType.SEASON_WRAP_OUTCOMES
        assert source_payload["champion"]["team"] == "UD Ibiza"
        assert [row["team"] for row in source_payload["playoff_rows"]] == ["CE Europa"]
        assert [row["team"] for row in source_payload["relegation_rows"]] == ["CE Sabadell"]
        assert "Descenso: CE Sabadell" in candidates[0].text_draft
    finally:
        session.close()
