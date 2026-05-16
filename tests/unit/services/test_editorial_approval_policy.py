from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from app.db.models import ContentCandidate
from app.services.editorial_approval_policy import (
    EditorialApprovalPolicyService,
    FRIDAY_AUTOAPPROVABLE_CONTENT_TYPES,
    MONDAY_AUTOAPPROVABLE_CONTENT_TYPES,
)
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


def test_autoapprove_includes_old_drafts_when_they_enter_release_window() -> None:
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
                id=902,
                competition_slug="tercera_rfef_g11",
                content_type="results_roundup",
                priority=90,
                text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 26",
                payload_json={
                    "reference_date": "2026-03-10",
                    "competition_name": "3a RFEF Baleares",
                    "content_key": "results_roundup:j26:older-draft",
                    "source_payload": {
                        "reference_date": "2026-03-10",
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
                source_summary_hash="approval-backfill-902",
                scheduled_at=None,
                status="draft",
                created_at=datetime(2026, 3, 10, 8, 30, tzinfo=timezone.utc),
                updated_at=datetime(2026, 3, 10, 8, 30, tzinfo=timezone.utc),
            )
        )
        session.commit()

        result = EditorialApprovalPolicyService(session, settings=build_settings()).autoapprove(
            reference_date=date(2026, 3, 17),
            dry_run=True,
        )

        rows = {row.id: row for row in result.rows}
        assert result.drafts_found == 1
        assert rows[902].autoapprovable is True
        assert rows[902].policy_reason == "policy_autoapprove_safe_type"
    finally:
        session.close()


def test_monday_autoapproves_top_scorer_update_when_configured() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Baleares",
            teams=["CD Manacor", "CE Mercadal"],
            standings_rows=[],
            match_rows=[],
        )
        session.add(
            ContentCandidate(
                id=903,
                competition_slug="tercera_rfef_g11",
                content_type="top_scorer_update",
                priority=75,
                text_draft="Pichichi provisional en 3a RFEF Baleares: Joan Serra (CD Manacor) manda con 8 goles.",
                payload_json={
                    "reference_date": "2026-03-16",
                    "competition_name": "3a RFEF Baleares",
                    "content_key": "top_scorer_update:tercera_rfef_g11:2025-26",
                    "source_payload": {
                        "leader": {"player": "Joan Serra", "team": "CD Manacor", "goals": 8},
                        "rows": [{"player": "Joan Serra", "team": "CD Manacor", "goals": 8}],
                        "leader_goals": 8,
                        "teams": ["CD Manacor"],
                        "season": "2025-26",
                    },
                },
                source_summary_hash="approval-top-scorer-903",
                status="draft",
                created_at=datetime(2026, 3, 16, 8, 30, tzinfo=timezone.utc),
                updated_at=datetime(2026, 3, 16, 8, 30, tzinfo=timezone.utc),
            )
        )
        session.commit()

        service = EditorialApprovalPolicyService(session, settings=build_settings())
        service.quality_service = Mock()
        service.quality_service.check_candidates.return_value = SimpleNamespace(
            rows=[SimpleNamespace(id=903, passed=True, errors=[])]
        )

        result = service.autoapprove(reference_date=date(2026, 3, 16), dry_run=True)

        rows = {row.id: row for row in result.rows}
        assert MONDAY_AUTOAPPROVABLE_CONTENT_TYPES == (rows[903].content_type,)
        assert rows[903].autoapprovable is True
        assert rows[903].policy_reason == "policy_autoapprove_safe_type"
    finally:
        session.close()


def test_friday_autoapproves_preview_and_match_impact_and_keeps_race_manual() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Baleares",
            teams=["CD Manacor", "CE Mercadal"],
            standings_rows=[],
            match_rows=[],
        )
        session.add_all(
            [
                ContentCandidate(
                    id=904,
                    competition_slug="tercera_rfef_g11",
                    content_type="featured_match_preview",
                    priority=80,
                    text_draft="PREVIA | 3a RFEF Baleares | CD Manacor vs CE Mercadal",
                    payload_json={"reference_date": "2026-03-20", "source_payload": {}},
                    source_summary_hash="approval-preview-904",
                    status="draft",
                    created_at=datetime(2026, 3, 20, 8, 30, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 3, 20, 8, 30, tzinfo=timezone.utc),
                ),
                ContentCandidate(
                    id=905,
                    competition_slug="tercera_rfef_g11",
                    content_type="match_impact_scenario",
                    priority=79,
                    text_draft="Si gana el CD Manacor, entra en playoff.",
                    payload_json={"reference_date": "2026-03-20", "source_payload": {}},
                    source_summary_hash="approval-impact-905",
                    status="draft",
                    created_at=datetime(2026, 3, 20, 8, 31, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 3, 20, 8, 31, tzinfo=timezone.utc),
                ),
                ContentCandidate(
                    id=906,
                    competition_slug="tercera_rfef_g11",
                    content_type="race_narrative",
                    priority=78,
                    text_draft="Tres equipos pelean por la ultima plaza de playoff.",
                    payload_json={"reference_date": "2026-03-20", "source_payload": {}},
                    source_summary_hash="approval-race-906",
                    status="draft",
                    created_at=datetime(2026, 3, 20, 8, 32, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 3, 20, 8, 32, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()

        service = EditorialApprovalPolicyService(session, settings=build_settings())
        service.quality_service = Mock()
        service.quality_service.check_candidates.return_value = SimpleNamespace(
            rows=[
                SimpleNamespace(id=904, passed=True, errors=[]),
                SimpleNamespace(id=905, passed=True, errors=[]),
            ]
        )

        result = service.autoapprove(reference_date=date(2026, 3, 20), dry_run=True)
        rows = {row.id: row for row in result.rows}

        assert set(FRIDAY_AUTOAPPROVABLE_CONTENT_TYPES) == {
            rows[904].content_type,
            rows[905].content_type,
        }
        assert rows[904].autoapprovable is True
        assert rows[905].autoapprovable is True
        assert rows[906].autoapprovable is False
        assert rows[906].policy_reason == "manual_review_policy"
    finally:
        session.close()
