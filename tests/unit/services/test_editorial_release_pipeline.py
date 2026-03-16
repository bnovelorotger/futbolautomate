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


def seed_release_candidates(session) -> None:
    now = datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc)
    session.add(
        Competition(
            code="tercera_rfef_g11",
            name="3a RFEF Grupo 11",
            normalized_name="3a rfef grupo 11",
            category_level=5,
            gender="male",
            region="Baleares",
            country="Spain",
            federation="RFEF",
            source_name="futbolme",
            source_competition_id="3065",
        )
    )
    session.flush()
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
                content_type="standings",
                priority=80,
                text_draft="CLASIFICACION\n\n1. RCD Mallorca B - 58 pts",
                payload_json={},
                source_summary_hash="release-hash-102",
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


def build_release_service(session) -> EditorialReleasePipelineService:
    autoexport_service = TypefullyAutoexportService(
        session,
        policy=build_policy(enabled=True, phase=1),
        settings=build_settings(),
    )
    autoexport_service.export_service.publisher = Mock()
    autoexport_service.export_service.publisher.export_text.side_effect = [
        TypefullyDraftResponse(
            draft_id="draft-safe-101",
            social_set_id="social-set-1",
            exported_at=datetime(2026, 3, 16, 10, 5, tzinfo=timezone.utc),
            raw_response={"id": "draft-safe-101"},
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
        assert result.drafts_found == 4
        assert result.autoapprovable_count == 2
        assert result.manual_review_count == 2
        assert rows[101].autoapprovable is True
        assert rows[102].autoapprovable is True
        assert rows[103].autoapprovable is False
        assert rows[103].policy_reason == "manual_review_policy"
        assert rows[104].autoapprovable is False
        assert rows[104].policy_reason == "text_draft_empty"
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

        assert result.drafts_found == 5
        assert result.autoapprovable_count == 2
        assert result.autoapproved_count == 2
        assert result.manual_review_count == 3
        assert result.dispatched_count == 2
        assert result.autoexport_scanned_count == 2
        assert result.autoexport_exported_count == 2
        assert result.autoexport_blocked_count == 0
        assert session.get(ContentCandidate, 101).status == "published"
        assert session.get(ContentCandidate, 101).autoapproved is True
        assert session.get(ContentCandidate, 101).autoapproval_reason == "policy_autoapprove_safe_type"
        assert session.get(ContentCandidate, 101).external_publication_ref == "draft-safe-101"
        assert session.get(ContentCandidate, 102).external_publication_ref == "draft-safe-102"
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
        assert session.get(ContentCandidate, 105).quality_check_passed is None
    finally:
        session.close()
