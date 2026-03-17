from __future__ import annotations

from datetime import date

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
