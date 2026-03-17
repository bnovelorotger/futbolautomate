from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock

from app.channels.typefully.schemas import TypefullyDraftResponse
from app.db.models import Competition, ContentCandidate
from app.services.editorial_approval_policy import EditorialApprovalPolicyService
from app.services.editorial_release_pipeline import EditorialReleasePipelineService
from app.services.typefully_autoexport_service import TypefullyAutoexportService
from tests.unit.services.test_typefully_autoexport_service import build_policy
from tests.unit.services.test_typefully_export_service import build_session, build_settings
from tests.unit.services.test_editorial_narratives import seed_competition


def seed_release_candidates(session) -> None:
    now = datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc)
    seed_competition(
        session,
        code="tercera_rfef_g11",
        name="3a RFEF Grupo 11",
        teams=["CD Llosetense", "SD Portmany", "CE Mercadal", "RCD Mallorca B", "CD Manacor"],
        standings_rows=[
            {"position": 1, "team": "RCD Mallorca B", "played": 26, "wins": 18, "draws": 4, "losses": 4, "goals_for": 55, "goals_against": 20, "goal_difference": 35, "points": 58},
            {"position": 2, "team": "CD Llosetense", "played": 26, "wins": 16, "draws": 5, "losses": 5, "goals_for": 44, "goals_against": 21, "goal_difference": 23, "points": 53},
            {"position": 3, "team": "SD Portmany", "played": 26, "wins": 15, "draws": 4, "losses": 7, "goals_for": 39, "goals_against": 24, "goal_difference": 15, "points": 49},
            {"position": 4, "team": "CE Mercadal", "played": 26, "wins": 14, "draws": 4, "losses": 8, "goals_for": 35, "goals_against": 28, "goal_difference": 7, "points": 46},
            {"position": 5, "team": "CD Manacor", "played": 26, "wins": 13, "draws": 5, "losses": 8, "goals_for": 33, "goals_against": 26, "goal_difference": 7, "points": 44},
        ],
        match_rows=[
            {"round_name": "Jornada 26", "match_date": now.date(), "match_time": now.time(), "home_team": "CD Llosetense", "away_team": "SD Portmany", "home_score": 2, "away_score": 0},
            {"round_name": "Jornada 26", "match_date": now.date(), "match_time": now.time(), "home_team": "CD Llosetense", "away_team": "CE Mercadal", "home_score": 2, "away_score": 1},
        ],
    )
    session.add_all(
        [
            ContentCandidate(
                id=101,
                competition_slug="tercera_rfef_g11",
                content_type="match_result",
                priority=100,
                text_draft="RESULTADO FINAL\n\nCD Llosetense 2-0 SD Portmany",
                payload_json={},
                source_summary_hash="release-hash-101",
                scheduled_at=None,
                status="draft",
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=102,
                competition_slug="tercera_rfef_g11",
                content_type="standings_roundup",
                priority=80,
                text_draft=(
                    "CLASIFICACION | 3a RFEF Grupo 11 | Jornada 26\n\n"
                    "1. RCD Mallorca B - 58 pts\n"
                    "2. CD Llosetense - 53 pts [PO]\n"
                    "3. SD Portmany - 49 pts [PO]\n"
                    "4. CE Mercadal - 46 pts [PO]"
                ),
                payload_json={
                    "content_key": "standings_roundup:j26",
                    "source_payload": {
                        "group_label": "Jornada 26",
                        "selected_rows_count": 4,
                        "omitted_rows_count": 1,
                        "rows": [
                            {"position": 1, "team": "RCD Mallorca B", "points": 58},
                            {"position": 2, "team": "CD Llosetense", "points": 53, "zone_tag": "playoff"},
                            {"position": 3, "team": "SD Portmany", "points": 49, "zone_tag": "playoff"},
                            {"position": 4, "team": "CE Mercadal", "points": 46, "zone_tag": "playoff"},
                        ],
                    },
                },
                source_summary_hash="release-hash-102",
                scheduled_at=None,
                status="draft",
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=106,
                competition_slug="tercera_rfef_g11",
                content_type="results_roundup",
                priority=99,
                text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 26\n\nCD Llosetense 2-0 SD Portmany\nCD Manacor 2-1 CE Mercadal",
                payload_json={
                    "content_key": "results_roundup:j26",
                    "source_payload": {
                        "group_label": "Jornada 26",
                        "selected_matches_count": 2,
                        "omitted_matches_count": 0,
                        "matches": [
                            {"home_team": "CD Llosetense", "away_team": "SD Portmany", "home_score": 2, "away_score": 0},
                            {"home_team": "CD Manacor", "away_team": "CE Mercadal", "home_score": 2, "away_score": 1},
                        ],
                    },
                },
                source_summary_hash="release-hash-106",
                scheduled_at=None,
                status="draft",
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=103,
                competition_slug="tercera_rfef_g11",
                content_type="viral_story",
                priority=70,
                text_draft="CD Manacor llega con 3 victorias seguidas en 3a RFEF Baleares.",
                payload_json={
                    "content_key": "viral:win_streak:cd-manacor",
                    "source_payload": {
                        "story_type": "win_streak",
                        "teams": ["CD Manacor"],
                        "streak_length": 3,
                        "metric_value": 3,
                    },
                },
                source_summary_hash="release-hash-103",
                scheduled_at=None,
                status="draft",
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=104,
                competition_slug="tercera_rfef_g11",
                content_type="preview",
                priority=90,
                text_draft="   ",
                payload_json={},
                source_summary_hash="release-hash-104",
                scheduled_at=None,
                status="draft",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()


def add_critical_narrative_candidates(session) -> None:
    now = datetime(2026, 3, 16, 10, 2, tzinfo=timezone.utc)
    session.add_all(
        [
            ContentCandidate(
                id=107,
                competition_slug="tercera_rfef_g11",
                content_type="featured_match_event",
                priority=96,
                text_draft="Pulso por el liderato en 3a RFEF Baleares: CD Llosetense y RCD Mallorca B llegan a la zona alta.",
                payload_json={
                    "content_key": "featured_match_event:llosetense-mallorca-b:top",
                    "source_payload": {
                        "home_team": "CD Llosetense",
                        "away_team": "RCD Mallorca B",
                        "teams": ["CD Llosetense", "RCD Mallorca B"],
                        "importance_score": 92,
                        "tags": ["title_race", "hot_form_match", "direct_rivalry"],
                        "home_recent_points": 11,
                        "away_recent_points": 13,
                    },
                },
                source_summary_hash="release-hash-107",
                scheduled_at=None,
                status="draft",
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=108,
                competition_slug="tercera_rfef_g11",
                content_type="viral_story",
                priority=94,
                text_draft="CD Manacor llega con 3 victorias seguidas en 3a RFEF Baleares.",
                payload_json={
                    "content_key": "viral:win_streak:cd-manacor:release",
                    "source_payload": {
                        "story_type": "win_streak",
                        "team": "CD Manacor",
                        "teams": ["CD Manacor"],
                        "metric_value": 3,
                        "streak_length": 3,
                    },
                },
                source_summary_hash="release-hash-108",
                scheduled_at=None,
                status="draft",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()


def build_release_service(session) -> EditorialReleasePipelineService:
    autoexport_service = TypefullyAutoexportService(
        session,
        policy=build_policy(enabled=True, phase=1),
        settings=build_settings(),
    )
    autoexport_service.export_service.publisher = Mock()
    autoexport_service.export_service.publisher.export_text.side_effect = [
        TypefullyDraftResponse(
            draft_id="draft-safe-106",
            social_set_id="social-set-1",
            exported_at=datetime(2026, 3, 16, 10, 5, tzinfo=timezone.utc),
            raw_response={"id": "draft-safe-106"},
            dry_run=False,
        ),
        TypefullyDraftResponse(
            draft_id="draft-safe-102",
            social_set_id="social-set-1",
            exported_at=datetime(2026, 3, 16, 10, 6, tzinfo=timezone.utc),
            raw_response={"id": "draft-safe-102"},
            dry_run=False,
        ),
    ]
    return EditorialReleasePipelineService(
        session,
        settings=build_settings(),
        autoexport_service=autoexport_service,
    )


def add_quality_blocked_candidate(session) -> None:
    now = datetime(2026, 3, 16, 10, 1, tzinfo=timezone.utc)
    session.add(
        ContentCandidate(
            id=105,
            competition_slug="tercera_rfef_g11",
            content_type="preview",
            priority=85,
            text_draft="P" * 400,
            payload_json={},
            source_summary_hash="release-hash-105",
            scheduled_at=None,
            status="draft",
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_editorial_approval_policy_marks_safe_types_and_blocks_sensitive() -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        result = EditorialApprovalPolicyService(session, settings=build_settings()).autoapprove(dry_run=True)

        rows = {row.id: row for row in result.rows}
        assert result.drafts_found == 5
        assert result.autoapprovable_count == 2
        assert result.manual_review_count == 3
        assert rows[101].autoapprovable is False
        assert rows[101].policy_reason == "manual_review_policy"
        assert rows[102].autoapprovable is True
        assert rows[106].autoapprovable is True
        assert rows[102].content_type.value == "standings_roundup"
        assert rows[103].autoapprovable is False
        assert rows[103].policy_reason == "manual_review_policy"
        assert rows[104].autoapprovable is False
        assert rows[104].policy_reason == "text_draft_empty"
    finally:
        session.close()


def test_editorial_approval_policy_keeps_narratives_in_manual_review() -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        add_critical_narrative_candidates(session)

        result = EditorialApprovalPolicyService(session, settings=build_settings()).autoapprove(dry_run=True)

        rows = {row.id: row for row in result.rows}
        assert rows[107].autoapprovable is False
        assert rows[107].policy_reason == "manual_review_policy"
        assert rows[108].autoapprovable is False
        assert rows[108].policy_reason == "manual_review_policy"
    finally:
        session.close()


def test_editorial_release_pipeline_real_run_exports_only_safe_drafts() -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        add_quality_blocked_candidate(session)
        service = build_release_service(session)

        result = service.run(dry_run=False)
        session.commit()

        assert result.drafts_found == 6
        assert result.autoapprovable_count == 2
        assert result.autoapproved_count == 2
        assert result.manual_review_count == 4
        assert result.dispatched_count == 2
        assert result.autoexport_scanned_count == 2
        assert result.autoexport_exported_count == 2
        assert result.autoexport_blocked_count == 0
        assert session.get(ContentCandidate, 101).status == "draft"
        assert session.get(ContentCandidate, 101).autoapproved is None
        assert session.get(ContentCandidate, 101).external_publication_ref is None
        assert session.get(ContentCandidate, 102).external_publication_ref == "draft-safe-102"
        assert session.get(ContentCandidate, 106).external_publication_ref == "draft-safe-106"
        assert session.get(ContentCandidate, 102).status == "published"
        assert session.get(ContentCandidate, 103).status == "draft"
        assert session.get(ContentCandidate, 103).external_publication_ref is None
        assert session.get(ContentCandidate, 104).status == "draft"
        assert session.get(ContentCandidate, 105).status == "draft"
        assert session.get(ContentCandidate, 105).quality_check_passed is False
    finally:
        session.close()


def test_editorial_release_pipeline_dry_run_does_not_persist_changes() -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        add_quality_blocked_candidate(session)
        service = build_release_service(session)

        result = service.run(dry_run=True)

        assert result.autoapproved_count == 2
        assert result.dispatched_count == 2
        assert result.autoexport_exported_count == 2
        assert session.get(ContentCandidate, 101).status == "draft"
        assert session.get(ContentCandidate, 101).autoapproved is None
        assert session.get(ContentCandidate, 101).external_publication_ref is None
        assert session.get(ContentCandidate, 106).external_publication_ref is None
        assert session.get(ContentCandidate, 105).quality_check_passed is None
    finally:
        session.close()


def test_editorial_release_pipeline_keeps_narratives_manual_in_v1() -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        add_critical_narrative_candidates(session)
        service = build_release_service(session)
        service.autoexport_service.export_service.publisher.export_text.side_effect = [
            TypefullyDraftResponse(
                draft_id="draft-safe-106",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 16, 10, 5, tzinfo=timezone.utc),
                raw_response={"id": "draft-safe-106"},
                dry_run=False,
            ),
            TypefullyDraftResponse(
                draft_id="draft-safe-102",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 16, 10, 6, tzinfo=timezone.utc),
                raw_response={"id": "draft-safe-102"},
                dry_run=False,
            ),
            TypefullyDraftResponse(
                draft_id="draft-safe-107",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 16, 10, 7, tzinfo=timezone.utc),
                raw_response={"id": "draft-safe-107"},
                dry_run=False,
            ),
        ]

        result = service.run(dry_run=False)
        session.commit()

        assert result.autoapprovable_count == 2
        assert result.autoapproved_count == 2
        assert result.dispatched_count == 2
        assert result.autoexport_exported_count == 2
        assert session.get(ContentCandidate, 107).status == "draft"
        assert session.get(ContentCandidate, 107).external_publication_ref is None
        assert session.get(ContentCandidate, 106).external_publication_ref is not None
        assert session.get(ContentCandidate, 102).external_publication_ref is not None
        assert session.get(ContentCandidate, 108).status == "draft"
        assert session.get(ContentCandidate, 108).external_publication_ref is None
    finally:
        session.close()
