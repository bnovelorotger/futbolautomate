from __future__ import annotations

from datetime import date, time

from sqlalchemy import select

from app.core.enums import ContentType, FormEventType
from app.db.models import ContentCandidate
from app.services.team_form import TeamFormService
from tests.unit.services.test_editorial_narratives import build_session, seed_competition


def seed_form_data(session) -> None:
    seed_competition(
        session,
        code="tercera_rfef_g11",
        name="3a RFEF Grupo 11",
        teams=["CE Alpha", "CE Beta", "CE Gamma", "CE Delta", "CE Epsilon", "CE Foxtrot", "CE Golf"],
        standings_rows=[
            {"position": 1, "team": "CE Alpha", "played": 26, "wins": 16, "draws": 5, "losses": 5, "goals_for": 44, "goals_against": 21, "goal_difference": 23, "points": 53},
            {"position": 2, "team": "CE Beta", "played": 26, "wins": 16, "draws": 4, "losses": 6, "goals_for": 39, "goals_against": 19, "goal_difference": 20, "points": 52},
            {"position": 3, "team": "CE Gamma", "played": 26, "wins": 14, "draws": 6, "losses": 6, "goals_for": 37, "goals_against": 25, "goal_difference": 12, "points": 48},
            {"position": 4, "team": "CE Delta", "played": 26, "wins": 9, "draws": 6, "losses": 11, "goals_for": 28, "goals_against": 35, "goal_difference": -7, "points": 33},
            {"position": 5, "team": "CE Epsilon", "played": 26, "wins": 8, "draws": 7, "losses": 11, "goals_for": 26, "goals_against": 33, "goal_difference": -7, "points": 31},
            {"position": 6, "team": "CE Golf", "played": 26, "wins": 7, "draws": 6, "losses": 13, "goals_for": 24, "goals_against": 34, "goal_difference": -10, "points": 27},
            {"position": 7, "team": "CE Foxtrot", "played": 26, "wins": 5, "draws": 4, "losses": 17, "goals_for": 18, "goals_against": 41, "goal_difference": -23, "points": 19},
        ],
        match_rows=[
            {"round_name": "Jornada 26", "match_date": date(2026, 3, 15), "match_time": time(18, 0), "home_team": "CE Alpha", "away_team": "CE Delta", "home_score": 2, "away_score": 0},
            {"round_name": "Jornada 26", "match_date": date(2026, 3, 15), "match_time": time(18, 15), "home_team": "CE Beta", "away_team": "CE Epsilon", "home_score": 1, "away_score": 0},
            {"round_name": "Jornada 26", "match_date": date(2026, 3, 15), "match_time": time(18, 30), "home_team": "CE Gamma", "away_team": "CE Foxtrot", "home_score": 2, "away_score": 1},
            {"round_name": "Jornada 25", "match_date": date(2026, 3, 8), "match_time": time(17, 0), "home_team": "CE Epsilon", "away_team": "CE Alpha", "home_score": 0, "away_score": 1},
            {"round_name": "Jornada 25", "match_date": date(2026, 3, 8), "match_time": time(17, 15), "home_team": "CE Beta", "away_team": "CE Foxtrot", "home_score": 2, "away_score": 0},
            {"round_name": "Jornada 25", "match_date": date(2026, 3, 8), "match_time": time(17, 30), "home_team": "CE Gamma", "away_team": "CE Delta", "home_score": 3, "away_score": 0},
            {"round_name": "Jornada 24", "match_date": date(2026, 3, 1), "match_time": time(16, 0), "home_team": "CE Alpha", "away_team": "CE Foxtrot", "home_score": 2, "away_score": 1},
            {"round_name": "Jornada 24", "match_date": date(2026, 3, 1), "match_time": time(16, 15), "home_team": "CE Beta", "away_team": "CE Delta", "home_score": 1, "away_score": 0},
            {"round_name": "Jornada 24", "match_date": date(2026, 3, 1), "match_time": time(16, 30), "home_team": "CE Epsilon", "away_team": "CE Gamma", "home_score": 0, "away_score": 2},
            {"round_name": "Jornada 23", "match_date": date(2026, 2, 22), "match_time": time(12, 0), "home_team": "CE Alpha", "away_team": "CE Beta", "home_score": 1, "away_score": 1},
            {"round_name": "Jornada 23", "match_date": date(2026, 2, 22), "match_time": time(12, 15), "home_team": "CE Gamma", "away_team": "CE Delta", "home_score": 1, "away_score": 1},
            {"round_name": "Jornada 23", "match_date": date(2026, 2, 22), "match_time": time(12, 30), "home_team": "CE Epsilon", "away_team": "CE Foxtrot", "home_score": 2, "away_score": 0},
            {"round_name": "Jornada 22", "match_date": date(2026, 2, 15), "match_time": time(12, 0), "home_team": "CE Alpha", "away_team": "CE Gamma", "home_score": 3, "away_score": 1},
            {"round_name": "Jornada 22", "match_date": date(2026, 2, 15), "match_time": time(12, 15), "home_team": "CE Beta", "away_team": "CE Golf", "home_score": 1, "away_score": 0},
            {"round_name": "Jornada 22", "match_date": date(2026, 2, 15), "match_time": time(12, 30), "home_team": "CE Delta", "away_team": "CE Epsilon", "home_score": 0, "away_score": 0},
            {"round_name": "Jornada 21", "match_date": date(2026, 2, 8), "match_time": time(12, 0), "home_team": "CE Golf", "away_team": "CE Foxtrot", "home_score": 1, "away_score": 0},
        ],
    )


def test_team_form_builds_recent_sequences_and_ranking_order() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        service = TeamFormService(session)

        result = service.ranking_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 16))

        assert [row.team for row in result.rows[:3]] == ["CE Alpha", "CE Beta", "CE Gamma"]
        alpha = result.rows[0]
        beta = result.rows[1]
        foxtrot = next(row for row in result.rows if row.team == "CE Foxtrot")
        assert alpha.sequence == "WWWDW"
        assert alpha.points == 13
        assert beta.points == 13
        assert alpha.goal_difference > beta.goal_difference
        assert foxtrot.sequence == "LLLLL"
        assert foxtrot.points == 0
    finally:
        session.close()


def test_team_form_detects_best_worst_and_recent_streak_events() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        service = TeamFormService(session)

        result = service.preview_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 16))

        events = {(event.event_type, event.team) for event in result.events}
        assert (FormEventType.BEST_FORM_TEAM, "CE Alpha") in events
        assert (FormEventType.WORST_FORM_TEAM, "CE Foxtrot") in events
        assert (FormEventType.LONGEST_WIN_STREAK_RECENT, "CE Alpha") in events
        assert (FormEventType.LONGEST_LOSS_STREAK_RECENT, "CE Foxtrot") in events
    finally:
        session.close()


def test_team_form_generate_persists_form_ranking_and_form_event_candidates() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        service = TeamFormService(session)

        result = service.generate_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 16))
        session.commit()

        rows = session.execute(select(ContentCandidate).order_by(ContentCandidate.id.asc())).scalars().all()

        assert result.stats.found == 5
        assert result.stats.inserted == 5
        assert {row.content_type for row in rows} == {"form_ranking", "form_event"}
        assert all(row.competition_slug == "tercera_rfef_g11" for row in rows)
        ranking_row = next(row for row in rows if row.content_type == str(ContentType.FORM_RANKING))
        assert "Forma ultimos 5 partidos en 3a RFEF Baleares" in ranking_row.text_draft
        assert "1. CE Alpha -> WWWDW (13 pts)" in ranking_row.text_draft
    finally:
        session.close()
