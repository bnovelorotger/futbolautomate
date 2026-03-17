from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.core.enums import ContentType
from app.db.models import ContentCandidate
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
