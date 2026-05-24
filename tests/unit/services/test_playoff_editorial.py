from __future__ import annotations

from datetime import date, time

from app.core.enums import ContentType
from app.db.models import ContentCandidate
from app.services.playoff_bracket_image_mapper import build_playoff_bracket_image_context
from app.services.playoff_editorial import PlayoffEditorialService
from tests.unit.services.test_editorial_narratives import build_session, seed_competition
from tests.unit.services.test_match_importance import add_scheduled_match


def test_playoff_featured_preview_does_not_require_standings() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="division_honor_mallorca_playoff",
            name="Division Honor Mallorca Playoff",
            teams=["CE Alpha", "CE Beta"],
            standings_rows=[],
            match_rows=[],
        )
        add_scheduled_match(
            session,
            competition_code="division_honor_mallorca_playoff",
            external_id="po-preview",
            match_date=date(2026, 5, 24),
            match_time=time(19, 0),
            home_team="CE Alpha",
            away_team="CE Beta",
        )

        candidates = PlayoffEditorialService(session).build_featured_preview_drafts(
            "division_honor_mallorca_playoff",
            reference_date=date(2026, 5, 24),
        )

        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.content_type == ContentType.FEATURED_MATCH_PREVIEW
        assert "PREVIA |" in candidate.text_draft
        assert candidate.payload_json["source_payload"]["editorial_phase"] == "playoffs"
        assert candidate.payload_json["source_payload"]["featured_match"]["home_team"] == "CE Alpha"
    finally:
        session.close()


def test_playoff_bracket_builds_image_ready_payload_with_finished_and_pending_matches() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="division_honor_mallorca_playoff",
            name="Division Honor Mallorca Playoff",
            teams=["CE Alpha", "CE Beta", "CE Gamma"],
            standings_rows=[],
            match_rows=[
                {
                    "round_name": None,
                    "match_date": date(2026, 5, 23),
                    "match_time": time(18, 0),
                    "home_team": "CE Alpha",
                    "away_team": "CE Beta",
                    "home_score": 2,
                    "away_score": 1,
                },
            ],
        )
        add_scheduled_match(
            session,
            competition_code="division_honor_mallorca_playoff",
            external_id="po-pending",
            match_date=date(2026, 5, 24),
            match_time=time(19, 0),
            home_team="CE Beta",
            away_team="CE Gamma",
        )

        candidates = PlayoffEditorialService(session).build_bracket_drafts(
            "division_honor_mallorca_playoff",
            reference_date=date(2026, 5, 24),
        )

        assert len(candidates) == 1
        candidate = candidates[0]
        source_payload = candidate.payload_json["source_payload"]
        assert candidate.content_type == ContentType.PLAYOFF_BRACKET
        assert candidate.payload_json["media"]["kind"] == "playoff_bracket"
        assert source_payload["finished_matches_count"] == 1
        assert source_payload["pending_matches_count"] == 1
        assert source_payload["bracket_rounds"]
        assert source_payload["matches"][0]["home_team"] == "CE Alpha"

        image_context = build_playoff_bracket_image_context(
            ContentCandidate(id=55, **candidate.model_dump(mode="python"))
        )
        assert image_context["title"] == "BRACKET PLAYOFF"
        assert image_context["total_matches"] == 2
        assert image_context["rounds"][0]["matches"][0]["score"] == "2-1"
    finally:
        session.close()
