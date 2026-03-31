from __future__ import annotations

from datetime import date, time

from sqlalchemy import select

from app.core.enums import ContentType
from app.db.models import ContentCandidate
from app.services.results_roundup import ResultsRoundupService
from tests.unit.services.test_editorial_narratives import build_session, seed_competition, seed_narratives_data
from tests.unit.services.test_team_form import seed_form_data


def test_results_roundup_groups_latest_round_and_orders_matches() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        result = ResultsRoundupService(session).show_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )

        assert result.group_label == "Jornada 26"
        assert result.selected_matches_count == 3
        assert result.omitted_matches_count == 0
        assert result.text_draft is not None
        assert "RESULTADOS | 3a RFEF Baleares | Jornada 26" in result.text_draft
        assert "CE Alpha 2-0 CE Delta" in result.text_draft
        assert "CE Beta 1-0 CE Epsilon" in result.text_draft
        assert "CE Gamma 2-1 CE Foxtrot" in result.text_draft
        assert [match.home_team for match in result.matches] == ["CE Alpha", "CE Beta", "CE Gamma"]
    finally:
        session.close()


def test_results_roundup_does_not_mix_competitions() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        result = ResultsRoundupService(session).show_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )

        assert result.text_draft is not None
        assert "Torrent CF" not in result.text_draft
        assert "UE Porreres" not in result.text_draft
    finally:
        session.close()


def test_results_roundup_generate_persists_results_roundup_candidate() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        result = ResultsRoundupService(session).generate_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )
        session.commit()

        rows = session.execute(select(ContentCandidate).order_by(ContentCandidate.id.asc())).scalars().all()

        assert result.stats.found == 1
        assert result.stats.inserted == 1
        assert len(rows) == 1
        assert rows[0].content_type == str(ContentType.RESULTS_ROUNDUP)
        assert rows[0].status == "draft"
        assert "RESULTADOS | 3a RFEF Baleares | Jornada 26" in rows[0].text_draft
    finally:
        session.close()


def test_results_roundup_reuses_existing_candidate_for_same_block_across_dates() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        service = ResultsRoundupService(session)

        first = service.generate_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 16))
        second = service.generate_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 17))
        session.commit()

        rows = session.execute(select(ContentCandidate).order_by(ContentCandidate.id.asc())).scalars().all()

        assert first.stats.inserted == 1
        assert second.stats.inserted == 0
        assert second.stats.updated == 1
        assert len(rows) == 1
    finally:
        session.close()


def test_results_roundup_handles_empty_competition_cleanly() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="division_honor_mallorca",
            name="Division de Honor Mallorca",
            teams=["CE Uno", "CE Dos"],
            standings_rows=[
                {"position": 1, "team": "CE Uno", "played": 0, "wins": 0, "draws": 0, "losses": 0, "goals_for": 0, "goals_against": 0, "goal_difference": 0, "points": 0},
                {"position": 2, "team": "CE Dos", "played": 0, "wins": 0, "draws": 0, "losses": 0, "goals_for": 0, "goals_against": 0, "goal_difference": 0, "points": 0},
            ],
            match_rows=[],
        )
        result = ResultsRoundupService(session).show_for_competition(
            "division_honor_mallorca",
            reference_date=date(2026, 3, 16),
        )

        assert result.selected_matches_count == 0
        assert result.omitted_matches_count == 0
        assert result.text_draft is None
        assert result.matches == []
    finally:
        session.close()


def test_results_roundup_respects_max_characters_and_truncates_cleanly() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        result = ResultsRoundupService(
            session,
            max_characters=90,
        ).show_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )

        assert result.text_draft is not None
        assert len(result.text_draft) <= 90
        assert result.selected_matches_count >= 1
        assert result.omitted_matches_count >= 1
    finally:
        session.close()


def test_results_roundup_filters_primera_rfef_to_ud_ibiza() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="primera_rfef_baleares",
            name="Primera Federacion Grupo 2",
            teams=[
                "UD Ibiza",
                "AD Ceuta FC",
                "CE Sabadell FC",
                "Marbella FC",
            ],
            standings_rows=[
                {"position": 1, "team": "CE Sabadell FC", "played": 29, "wins": 16, "draws": 6, "losses": 7, "goals_for": 40, "goals_against": 23, "goal_difference": 17, "points": 54},
                {"position": 12, "team": "AD Ceuta FC", "played": 29, "wins": 10, "draws": 9, "losses": 10, "goals_for": 31, "goals_against": 30, "goal_difference": 1, "points": 39},
                {"position": 13, "team": "UD Ibiza", "played": 29, "wins": 10, "draws": 8, "losses": 11, "goals_for": 28, "goals_against": 30, "goal_difference": -2, "points": 38},
                {"position": 17, "team": "Marbella FC", "played": 29, "wins": 8, "draws": 8, "losses": 13, "goals_for": 25, "goals_against": 35, "goal_difference": -10, "points": 32},
            ],
            match_rows=[
                {"round_name": "Jornada 29", "match_date": date(2026, 3, 22), "match_time": time(12, 0), "home_team": "UD Ibiza", "away_team": "AD Ceuta FC", "home_score": 1, "away_score": 0},
                {"round_name": "Jornada 29", "match_date": date(2026, 3, 22), "match_time": time(18, 0), "home_team": "CE Sabadell FC", "away_team": "Marbella FC", "home_score": 2, "away_score": 1},
            ],
        )
        result = ResultsRoundupService(session).show_for_competition(
            "primera_rfef_baleares",
            reference_date=date(2026, 3, 23),
        )

        assert result.text_draft is not None
        assert "UD Ibiza 1-0 AD Ceuta FC" in result.text_draft
        assert "CE Sabadell FC" not in result.text_draft
        assert result.selected_matches_count == 1
    finally:
        session.close()


def test_results_roundup_generates_single_candidate_for_five_match_round() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="division_honor_mallorca",
            name="Division Honor Mallorca",
            teams=[
                "CE Uno",
                "CE Dos",
                "CE Tres",
                "CE Cuatro",
                "CE Cinco",
                "CE Seis",
                "CE Siete",
                "CE Ocho",
                "CE Nueve",
                "CE Diez",
            ],
            standings_rows=[
                {"position": 1, "team": "CE Uno", "played": 10, "wins": 8, "draws": 1, "losses": 1, "goals_for": 20, "goals_against": 6, "goal_difference": 14, "points": 25},
                {"position": 2, "team": "CE Dos", "played": 10, "wins": 7, "draws": 1, "losses": 2, "goals_for": 18, "goals_against": 8, "goal_difference": 10, "points": 22},
                {"position": 3, "team": "CE Tres", "played": 10, "wins": 6, "draws": 2, "losses": 2, "goals_for": 17, "goals_against": 10, "goal_difference": 7, "points": 20},
                {"position": 4, "team": "CE Cuatro", "played": 10, "wins": 6, "draws": 1, "losses": 3, "goals_for": 15, "goals_against": 11, "goal_difference": 4, "points": 19},
                {"position": 5, "team": "CE Cinco", "played": 10, "wins": 5, "draws": 2, "losses": 3, "goals_for": 14, "goals_against": 12, "goal_difference": 2, "points": 17},
                {"position": 6, "team": "CE Seis", "played": 10, "wins": 4, "draws": 3, "losses": 3, "goals_for": 13, "goals_against": 13, "goal_difference": 0, "points": 15},
                {"position": 7, "team": "CE Siete", "played": 10, "wins": 4, "draws": 1, "losses": 5, "goals_for": 12, "goals_against": 14, "goal_difference": -2, "points": 13},
                {"position": 8, "team": "CE Ocho", "played": 10, "wins": 3, "draws": 2, "losses": 5, "goals_for": 11, "goals_against": 15, "goal_difference": -4, "points": 11},
                {"position": 9, "team": "CE Nueve", "played": 10, "wins": 2, "draws": 2, "losses": 6, "goals_for": 10, "goals_against": 18, "goal_difference": -8, "points": 8},
                {"position": 10, "team": "CE Diez", "played": 10, "wins": 1, "draws": 1, "losses": 8, "goals_for": 8, "goals_against": 21, "goal_difference": -13, "points": 4},
            ],
            match_rows=[
                {"round_name": "Jornada 10", "match_date": date(2026, 3, 15), "match_time": time(10, 0), "home_team": "CE Uno", "away_team": "CE Dos", "home_score": 2, "away_score": 1},
                {"round_name": "Jornada 10", "match_date": date(2026, 3, 15), "match_time": time(11, 0), "home_team": "CE Tres", "away_team": "CE Cuatro", "home_score": 1, "away_score": 0},
                {"round_name": "Jornada 10", "match_date": date(2026, 3, 15), "match_time": time(12, 0), "home_team": "CE Cinco", "away_team": "CE Seis", "home_score": 3, "away_score": 2},
                {"round_name": "Jornada 10", "match_date": date(2026, 3, 15), "match_time": time(13, 0), "home_team": "CE Siete", "away_team": "CE Ocho", "home_score": 0, "away_score": 0},
                {"round_name": "Jornada 10", "match_date": date(2026, 3, 15), "match_time": time(14, 0), "home_team": "CE Nueve", "away_team": "CE Diez", "home_score": 1, "away_score": 1},
            ],
        )
        result = ResultsRoundupService(session).generate_for_competition(
            "division_honor_mallorca",
            reference_date=date(2026, 3, 16),
        )

        assert len(result.generated_candidates) == 1
        assert result.generated_candidates[0].selected_matches_count == 5
        assert "(1/2)" not in result.generated_candidates[0].text_draft
        assert "(2/2)" not in result.generated_candidates[0].text_draft
    finally:
        session.close()
