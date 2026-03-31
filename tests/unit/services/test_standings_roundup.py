from __future__ import annotations

from datetime import date, time

from sqlalchemy import select

from app.core.enums import ContentType
from app.db.models import ContentCandidate
from app.services.editorial_formatter import EditorialFormatterService
from app.services.standings_roundup import StandingsRoundupService
from tests.unit.services.test_editorial_narratives import build_session, seed_competition, seed_narratives_data
from tests.unit.services.test_team_form import seed_form_data


def test_standings_roundup_builds_compact_table_with_zone_markers() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        result = StandingsRoundupService(session).show_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )

        assert result.group_label == "Jornada 26"
        assert result.selected_rows_count >= 5
        assert result.text_draft is not None
        assert "CLASIFICACION | 3a RFEF Baleares | Jornada 26" in result.text_draft
        assert "1. CE Alpha - 53 pts" in result.text_draft
        assert "2. CE Beta - 52 pts [PO]" in result.text_draft
        assert any(row.zone_tag == "playoff" for row in result.rows)
    finally:
        session.close()


def test_standings_roundup_does_not_mix_competitions() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        result = StandingsRoundupService(session).show_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )

        assert result.text_draft is not None
        assert "Torrent CF" not in result.text_draft
        assert "UE Porreres" not in result.text_draft
    finally:
        session.close()


def test_standings_roundup_generate_persists_candidate() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        result = StandingsRoundupService(session).generate_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )
        session.commit()

        rows = session.execute(select(ContentCandidate).order_by(ContentCandidate.id.asc())).scalars().all()

        assert result.stats.found == 1
        assert result.stats.inserted == 1
        assert len(rows) == 1
        assert rows[0].content_type == str(ContentType.STANDINGS_ROUNDUP)
        assert rows[0].status == "draft"
        assert "CLASIFICACION | 3a RFEF Baleares | Jornada 26" in rows[0].text_draft
    finally:
        session.close()


def test_standings_roundup_generates_single_candidate_and_keeps_round_name_for_formatter() -> None:
    session = build_session()
    try:
        teams = [f"Equipo {index}" for index in range(1, 16)]
        standings_rows = [
            {
                "position": index,
                "team": team_name,
                "played": 25 if index == 5 else 26,
                "wins": max(0, 16 - index),
                "draws": 4,
                "losses": index,
                "goals_for": max(10, 35 - index),
                "goals_against": 10 + index,
                "goal_difference": 20 - index,
                "points": max(1, 60 - (index * 2)),
            }
            for index, team_name in enumerate(teams, start=1)
        ]
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Grupo 11",
            teams=teams,
            standings_rows=standings_rows,
            match_rows=[
                {"round_name": "Jornada 26", "match_date": date(2026, 3, 16), "match_time": time(18, 0), "home_team": "Equipo 1", "away_team": "Equipo 2", "home_score": 2, "away_score": 1},
                {"round_name": "Jornada 26", "match_date": date(2026, 3, 16), "match_time": time(18, 15), "home_team": "Equipo 14", "away_team": "Equipo 15", "home_score": 1, "away_score": 0},
            ],
        )

        candidates = StandingsRoundupService(session).build_candidate_drafts(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 17),
        )
        formatted_candidates = EditorialFormatterService(session).apply_to_drafts(candidates)

        assert len(formatted_candidates) == 1
        assert formatted_candidates[0].payload_json["source_payload"]["round_name"] == "Jornada 26"
        assert formatted_candidates[0].formatted_text is not None
        assert formatted_candidates[0].formatted_text.startswith("📊 Clasificación - 3ª RFEF - G11 - J26")
        assert "(1/2)" not in formatted_candidates[0].formatted_text
        assert "(2/2)" not in formatted_candidates[0].formatted_text
    finally:
        session.close()


def test_standings_roundup_supports_new_integrated_competitions() -> None:
    session = build_session()
    try:
        cases = [
            ("division_honor_ibiza_form", "Division Honor Ibiza/Form"),
            ("division_honor_menorca", "Division Honor Menorca"),
            ("tercera_federacion_femenina_g11", "3a RFEF Femenina Grupo 11"),
        ]
        for competition_code, competition_name in cases:
            seed_competition(
                session,
                code=competition_code,
                name=competition_name,
                teams=["Equipo 1", "Equipo 2", "Equipo 3", "Equipo 4", "Equipo 5", "Equipo 6"],
                standings_rows=[
                    {"position": 1, "team": "Equipo 1", "played": 12, "wins": 9, "draws": 2, "losses": 1, "goals_for": 21, "goals_against": 9, "goal_difference": 12, "points": 29},
                    {"position": 2, "team": "Equipo 2", "played": 12, "wins": 8, "draws": 2, "losses": 2, "goals_for": 19, "goals_against": 10, "goal_difference": 9, "points": 26},
                    {"position": 3, "team": "Equipo 3", "played": 12, "wins": 7, "draws": 2, "losses": 3, "goals_for": 18, "goals_against": 12, "goal_difference": 6, "points": 23},
                    {"position": 4, "team": "Equipo 4", "played": 12, "wins": 6, "draws": 2, "losses": 4, "goals_for": 15, "goals_against": 13, "goal_difference": 2, "points": 20},
                    {"position": 5, "team": "Equipo 5", "played": 12, "wins": 4, "draws": 3, "losses": 5, "goals_for": 12, "goals_against": 14, "goal_difference": -2, "points": 15},
                    {"position": 6, "team": "Equipo 6", "played": 12, "wins": 3, "draws": 1, "losses": 8, "goals_for": 10, "goals_against": 21, "goal_difference": -11, "points": 10},
                ],
                match_rows=[],
            )

            result = StandingsRoundupService(session).generate_for_competition(
                competition_code,
                reference_date=date(2026, 3, 17),
            )

            assert len(result.generated_candidates) == 1
            assert result.generated_candidates[0].selected_rows_count >= 1
            assert "(1/2)" not in result.generated_candidates[0].text_draft
            assert "(2/2)" not in result.generated_candidates[0].text_draft
    finally:
        session.close()


def test_standings_roundup_filters_segunda_to_tracked_balearic_teams() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="segunda_rfef_g3_baleares",
            name="2a RFEF Grupo 3",
            teams=[
                "UE Sant Andreu",
                "CD Atlético Baleares",
                "UD Poblense",
                "Reus FC Reddis",
                "UE Porreres",
            ],
            standings_rows=[
                {"position": 1, "team": "UE Sant Andreu", "played": 26, "wins": 16, "draws": 6, "losses": 4, "goals_for": 39, "goals_against": 20, "goal_difference": 19, "points": 54},
                {"position": 2, "team": "CD Atlético Baleares", "played": 26, "wins": 15, "draws": 6, "losses": 5, "goals_for": 35, "goals_against": 18, "goal_difference": 17, "points": 51},
                {"position": 3, "team": "UD Poblense", "played": 26, "wins": 14, "draws": 6, "losses": 6, "goals_for": 31, "goals_against": 19, "goal_difference": 12, "points": 48},
                {"position": 4, "team": "Reus FC Reddis", "played": 26, "wins": 12, "draws": 6, "losses": 8, "goals_for": 28, "goals_against": 23, "goal_difference": 5, "points": 42},
                {"position": 5, "team": "UE Porreres", "played": 26, "wins": 11, "draws": 7, "losses": 8, "goals_for": 26, "goals_against": 24, "goal_difference": 2, "points": 40},
            ],
            match_rows=[
                {"round_name": "Jornada 26", "match_date": date(2026, 3, 16), "match_time": time(18, 0), "home_team": "CD Atlético Baleares", "away_team": "UE Sant Andreu", "home_score": 2, "away_score": 1},
                {"round_name": "Jornada 26", "match_date": date(2026, 3, 16), "match_time": time(18, 15), "home_team": "UE Porreres", "away_team": "Reus FC Reddis", "home_score": 1, "away_score": 1},
            ],
        )

        result = StandingsRoundupService(session).show_for_competition(
            "segunda_rfef_g3_baleares",
            reference_date=date(2026, 3, 17),
        )

        assert [row.team for row in result.rows] == [
            "CD Atlético Baleares",
            "UD Poblense",
            "UE Porreres",
        ]
        assert result.text_draft is not None
        assert "UE Sant Andreu" not in result.text_draft
        assert "Reus FC Reddis" not in result.text_draft
    finally:
        session.close()


def test_standings_roundup_reuses_existing_candidate_for_same_table_across_dates() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        service = StandingsRoundupService(session)

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


def test_standings_roundup_handles_competition_without_standings_cleanly() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="division_honor_mallorca",
            name="Division de Honor Mallorca",
            teams=["CE Uno", "CE Dos"],
            standings_rows=[],
            match_rows=[],
        )
        result = StandingsRoundupService(session).show_for_competition(
            "division_honor_mallorca",
            reference_date=date(2026, 3, 16),
        )

        assert result.selected_rows_count == 0
        assert result.omitted_rows_count == 0
        assert result.text_draft is None
        assert result.rows == []
    finally:
        session.close()


def test_standings_roundup_respects_max_characters() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        result = StandingsRoundupService(
            session,
            max_characters=120,
        ).show_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )

        assert result.text_draft is not None
        assert len(result.text_draft) <= 120
        assert result.selected_rows_count >= 1
        assert result.omitted_rows_count >= 1
    finally:
        session.close()
