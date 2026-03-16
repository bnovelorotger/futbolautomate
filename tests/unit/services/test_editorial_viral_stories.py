from __future__ import annotations

from datetime import date, time

from sqlalchemy import select

from app.core.enums import ViralStoryType
from app.db.models import ContentCandidate
from app.services.editorial_viral_stories import EditorialViralStoriesService
from tests.unit.services.test_editorial_narratives import build_session, seed_competition, seed_narratives_data


def seed_viral_extreme_data(session) -> None:
    seed_competition(
        session,
        code="division_honor_mallorca",
        name="Division Honor Mallorca",
        teams=["CE Alpha", "CE Beta", "CE Gamma", "CE Delta"],
        standings_rows=[
            {"position": 1, "team": "CE Alpha", "played": 12, "wins": 10, "draws": 1, "losses": 1, "goals_for": 30, "goals_against": 9, "goal_difference": 21, "points": 31},
            {"position": 2, "team": "CE Beta", "played": 12, "wins": 7, "draws": 2, "losses": 3, "goals_for": 23, "goals_against": 12, "goal_difference": 11, "points": 23},
            {"position": 3, "team": "CE Gamma", "played": 12, "wins": 6, "draws": 3, "losses": 3, "goals_for": 18, "goals_against": 7, "goal_difference": 11, "points": 21},
            {"position": 4, "team": "CE Delta", "played": 12, "wins": 2, "draws": 1, "losses": 9, "goals_for": 10, "goals_against": 28, "goal_difference": -18, "points": 7},
        ],
        match_rows=[
            {"round_name": "Jornada 14", "match_date": date(2026, 3, 15), "match_time": time(18, 0), "home_team": "CE Alpha", "away_team": "CE Delta", "home_score": 4, "away_score": 1},
            {"round_name": "Jornada 13", "match_date": date(2026, 3, 8), "match_time": time(17, 0), "home_team": "CE Beta", "away_team": "CE Delta", "home_score": 3, "away_score": 1},
            {"round_name": "Jornada 12", "match_date": date(2026, 3, 1), "match_time": time(16, 0), "home_team": "CE Delta", "away_team": "CE Gamma", "home_score": 0, "away_score": 3},
            {"round_name": "Jornada 11", "match_date": date(2026, 2, 22), "match_time": time(12, 0), "home_team": "CE Delta", "away_team": "CE Alpha", "home_score": 1, "away_score": 4},
            {"round_name": "Jornada 10", "match_date": date(2026, 2, 15), "match_time": time(11, 30), "home_team": "CE Gamma", "away_team": "CE Beta", "home_score": 2, "away_score": 2},
            {"round_name": "Jornada 9", "match_date": date(2026, 2, 8), "match_time": time(12, 0), "home_team": "CE Alpha", "away_team": "CE Beta", "home_score": 0, "away_score": 0},
            {"round_name": "Jornada 8", "match_date": date(2026, 2, 1), "match_time": time(12, 0), "home_team": "CE Alpha", "away_team": "CE Gamma", "home_score": 2, "away_score": 1},
        ],
    )


def seed_low_signal_data(session) -> None:
    seed_competition(
        session,
        code="division_honor_mallorca",
        name="Division Honor Mallorca",
        teams=["CE Uno", "CE Dos", "CE Tres", "CE Cuatro"],
        standings_rows=[
            {"position": 1, "team": "CE Uno", "played": 4, "wins": 2, "draws": 1, "losses": 1, "goals_for": 6, "goals_against": 4, "goal_difference": 2, "points": 7},
            {"position": 2, "team": "CE Dos", "played": 4, "wins": 2, "draws": 1, "losses": 1, "goals_for": 5, "goals_against": 4, "goal_difference": 1, "points": 7},
            {"position": 3, "team": "CE Tres", "played": 4, "wins": 1, "draws": 2, "losses": 1, "goals_for": 4, "goals_against": 4, "goal_difference": 0, "points": 5},
            {"position": 4, "team": "CE Cuatro", "played": 4, "wins": 1, "draws": 0, "losses": 3, "goals_for": 3, "goals_against": 6, "goal_difference": -3, "points": 3},
        ],
        match_rows=[
            {"round_name": "Jornada 4", "match_date": date(2026, 3, 15), "match_time": time(18, 0), "home_team": "CE Uno", "away_team": "CE Dos", "home_score": 1, "away_score": 1},
            {"round_name": "Jornada 3", "match_date": date(2026, 3, 8), "match_time": time(17, 0), "home_team": "CE Tres", "away_team": "CE Cuatro", "home_score": 1, "away_score": 0},
            {"round_name": "Jornada 2", "match_date": date(2026, 3, 1), "match_time": time(16, 0), "home_team": "CE Dos", "away_team": "CE Tres", "home_score": 1, "away_score": 1},
            {"round_name": "Jornada 1", "match_date": date(2026, 2, 22), "match_time": time(12, 0), "home_team": "CE Cuatro", "away_team": "CE Uno", "home_score": 0, "away_score": 1},
        ],
    )


def test_editorial_viral_stories_builds_expected_story_types() -> None:
    session = build_session()
    try:
        seed_viral_extreme_data(session)
        service = EditorialViralStoriesService(session)

        result = service.preview_for_competition("division_honor_mallorca", reference_date=date(2026, 3, 16))

        story_types = {row.story_type for row in result.rows}
        assert {
            ViralStoryType.UNBEATEN_STREAK,
            ViralStoryType.LOSING_STREAK,
            ViralStoryType.HOT_FORM,
            ViralStoryType.COLD_FORM,
            ViralStoryType.RECENT_TOP_SCORER,
            ViralStoryType.BEST_ATTACK,
            ViralStoryType.BEST_DEFENSE,
            ViralStoryType.GOALS_TREND,
        }.issubset(story_types)
        assert all("Torrent CF" not in row.text_draft and "UE Porreres" not in row.text_draft for row in result.rows)
    finally:
        session.close()


def test_editorial_viral_stories_respects_thresholds() -> None:
    session = build_session()
    try:
        seed_low_signal_data(session)
        service = EditorialViralStoriesService(session)

        result = service.preview_for_competition("division_honor_mallorca", reference_date=date(2026, 3, 16))

        assert result.rows == []
    finally:
        session.close()


def test_editorial_viral_stories_generate_persists_candidates_without_cross_competition_mix() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        service = EditorialViralStoriesService(session)

        result = service.generate_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 15))
        session.commit()

        rows = session.execute(select(ContentCandidate).order_by(ContentCandidate.id.asc())).scalars().all()

        assert result.stats.inserted == len(result.rows)
        assert rows
        assert all(row.competition_slug == "tercera_rfef_g11" for row in rows)
        assert all(row.content_type == "viral_story" for row in rows)
        assert all("Torrent CF" not in row.text_draft and "UE Porreres" not in row.text_draft for row in rows)
    finally:
        session.close()
