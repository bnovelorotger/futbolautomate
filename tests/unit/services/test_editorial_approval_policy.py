from __future__ import annotations

from datetime import date, datetime, timezone

from app.db.models import ContentCandidate
from app.services.editorial_approval_policy import EditorialApprovalPolicyService
from tests.unit.services.test_editorial_narratives import seed_competition
from tests.unit.services.service_test_support import build_session, build_settings


def test_autoapprove_includes_logical_reference_date_even_if_created_next_day() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Baleares",
            teams=["CD Llosetense", "SD Portmany"],
            standings_rows=[],
            match_rows=[
                {
                    "round_name": "Jornada 26",
                    "match_date": date(2026, 3, 16),
                    "match_time": datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc).time(),
                    "home_team": "CD Llosetense",
                    "away_team": "SD Portmany",
                    "home_score": 2,
                    "away_score": 0,
                }
            ],
        )
        session.add(
            ContentCandidate(
                id=901,
                competition_slug="tercera_rfef_g11",
                content_type="results_roundup",
                priority=90,
                text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 26",
                payload_json={
                    "reference_date": "2026-03-17",
                    "competition_name": "3a RFEF Baleares",
                    "content_key": "results_roundup:j26:test",
                    "source_payload": {
                        "reference_date": "2026-03-17",
                        "selected_matches_count": 1,
                        "omitted_matches_count": 0,
                        "group_label": "Jornada 26",
                        "matches": [
                            {
                                "round_name": "Jornada 26",
                                "match_date": "2026-03-16",
                                "home_team": "CD Llosetense",
                                "away_team": "SD Portmany",
                                "home_score": 2,
                                "away_score": 0,
                            }
                        ],
                    },
                },
                source_summary_hash="approval-backfill-901",
                scheduled_at=None,
                status="draft",
                created_at=datetime(2026, 3, 17, 8, 30, tzinfo=timezone.utc),
                updated_at=datetime(2026, 3, 17, 8, 30, tzinfo=timezone.utc),
            )
        )
        session.commit()

        result = EditorialApprovalPolicyService(session, settings=build_settings()).autoapprove(
            reference_date=date(2026, 3, 17),
            dry_run=True,
        )

        rows = {row.id: row for row in result.rows}
        assert result.drafts_found == 1
        assert rows[901].autoapprovable is True
        assert rows[901].policy_reason == "policy_autoapprove_safe_type"
    finally:
        session.close()
