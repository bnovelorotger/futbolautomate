from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest.mock import Mock

from typer.testing import CliRunner

from app.core.enums import ContentCandidateStatus
from app.pipelines import typefully_autoexport as typefully_autoexport_pipeline
from app.channels.typefully.client import TypefullyApiError
from app.channels.typefully.schemas import TypefullyDraftResponse
from app.core.enums import ContentType
from app.db.models import ContentCandidate
from app.schemas.typefully_autoexport import (
    TypefullyAutoexportCandidateView,
    TypefullyAutoexportLastRun,
    TypefullyAutoexportPhasePolicy,
    TypefullyAutoexportPolicy,
    TypefullyAutoexportStatusView,
)
from app.services.typefully_autoexport_service import TypefullyAutoexportService
from tests.unit.services.test_typefully_export_service import build_session, build_settings, seed_candidates


def seed_manual_only_candidates(session) -> None:
    now = datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            ContentCandidate(
                id=7,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="viral_story",
                priority=72,
                text_draft="Historia viral controlada",
                rewritten_text=None,
                rewrite_status=None,
                rewrite_model=None,
                rewrite_timestamp=None,
                rewrite_error=None,
                payload_json={},
                source_summary_hash="hash-7",
                scheduled_at=None,
                status="published",
                reviewed_at=now,
                approved_at=now,
                published_at=now,
                rejection_reason=None,
                external_publication_ref=None,
                external_channel=None,
                external_exported_at=None,
                external_publication_timestamp=None,
                external_publication_attempted_at=None,
                external_publication_error=None,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=8,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="metric_narrative",
                priority=66,
                text_draft="Narrativa metrica",
                rewritten_text=None,
                rewrite_status=None,
                rewrite_model=None,
                rewrite_timestamp=None,
                rewrite_error=None,
                payload_json={},
                source_summary_hash="hash-8",
                scheduled_at=None,
                status="published",
                reviewed_at=now,
                approved_at=now,
                published_at=now,
                rejection_reason=None,
                external_publication_ref=None,
                external_channel=None,
                external_exported_at=None,
                external_publication_timestamp=None,
                external_publication_attempted_at=None,
                external_publication_error=None,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()


def build_policy(enabled: bool = True, phase: int = 3) -> TypefullyAutoexportPolicy:
    return TypefullyAutoexportPolicy(
        enabled=enabled,
        phase=phase,
        default_limit=10,
        use_rewrite_by_default=True,
        max_text_length=280,
        duplicate_window_hours=72,
        max_line_breaks=6,
        max_exports_per_run=5,
        max_exports_per_day=None,
        stop_on_capacity_limit=True,
        capacity_error_codes=["MONETIZATION_ERROR"],
        allowed_content_types=[
            ContentType.MATCH_RESULT,
            ContentType.STANDINGS,
            ContentType.PREVIEW,
            ContentType.RANKING,
            ContentType.STAT_NARRATIVE,
            ContentType.METRIC_NARRATIVE,
            ContentType.VIRAL_STORY,
        ],
        manual_review_content_types=[],
        validation_required_content_types=[
            ContentType.STAT_NARRATIVE,
            ContentType.METRIC_NARRATIVE,
            ContentType.VIRAL_STORY,
        ],
        phases={
            1: TypefullyAutoexportPhasePolicy(
                allowed_content_types=[
                    ContentType.MATCH_RESULT,
                    ContentType.STANDINGS,
                    ContentType.PREVIEW,
                    ContentType.RANKING,
                ],
                validation_required_content_types=[],
            ),
            2: TypefullyAutoexportPhasePolicy(
                allowed_content_types=[
                    ContentType.MATCH_RESULT,
                    ContentType.STANDINGS,
                    ContentType.PREVIEW,
                    ContentType.RANKING,
                    ContentType.STAT_NARRATIVE,
                    ContentType.METRIC_NARRATIVE,
                ],
                validation_required_content_types=[
                    ContentType.STAT_NARRATIVE,
                    ContentType.METRIC_NARRATIVE,
                ],
            ),
            3: TypefullyAutoexportPhasePolicy(
                allowed_content_types=[
                    ContentType.MATCH_RESULT,
                    ContentType.STANDINGS,
                    ContentType.PREVIEW,
                    ContentType.RANKING,
                    ContentType.STAT_NARRATIVE,
                    ContentType.METRIC_NARRATIVE,
                    ContentType.VIRAL_STORY,
                ],
                validation_required_content_types=[
                    ContentType.STAT_NARRATIVE,
                    ContentType.METRIC_NARRATIVE,
                    ContentType.VIRAL_STORY,
                ],
            ),
        },
    )


def add_safe_candidate(session, candidate_id: int, text: str | None = None) -> None:
    now = datetime(2026, 3, 18, 10, 10, tzinfo=timezone.utc)
    session.add(
        ContentCandidate(
            id=candidate_id,
            competition_slug="segunda_rfef_g3_baleares",
            content_type="match_result",
            priority=90 - candidate_id,
            text_draft=text or f"RESULTADO FINAL Equipo {candidate_id} 1-0 Rival {candidate_id}",
            rewritten_text=None,
            rewrite_status=None,
            rewrite_model=None,
            rewrite_timestamp=None,
            rewrite_error=None,
            payload_json={},
            source_summary_hash=f"hash-{candidate_id}",
            scheduled_at=None,
            status="published",
            reviewed_at=now,
            approved_at=now,
            published_at=now,
            rejection_reason=None,
            external_publication_ref=None,
            external_channel=None,
            external_exported_at=None,
            external_publication_timestamp=None,
            external_publication_attempted_at=None,
            external_publication_error=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_typefully_autoexport_dry_run_applies_policy() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        seed_manual_only_candidates(session)
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True),
            settings=build_settings(),
        )

        result = service.run(dry_run=True, limit=10)

        assert result.phase == 3
        assert result.scanned_count == 5
        assert result.eligible_count == 2
        assert result.exported_count == 2
        assert result.blocked_count == 3
        assert result.capacity_deferred_count == 0
        assert {row.id for row in result.rows if row.autoexport_allowed} == {1, 6}
        assert {row.id for row in result.rows if not row.autoexport_allowed} == {5, 7, 8}
    finally:
        session.close()


def test_typefully_autoexport_phase_1_blocks_non_safe_types() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        seed_manual_only_candidates(session)
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1),
            settings=build_settings(),
        )

        rows = {row.id: row for row in service.list_candidates(limit=10)}

        assert rows[1].autoexport_allowed is True
        assert rows[6].autoexport_allowed is True
        assert rows[5].autoexport_allowed is False
        assert rows[5].policy_reason == "phase_1_not_allowed"
        assert rows[7].autoexport_allowed is False
        assert rows[7].policy_reason == "phase_1_not_allowed"
        assert rows[8].autoexport_allowed is False
        assert rows[8].policy_reason == "phase_1_not_allowed"
    finally:
        session.close()


def test_typefully_autoexport_real_run_exports_only_allowed_types_and_persists() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        seed_manual_only_candidates(session)
        publisher = Mock()
        publisher.export_text.side_effect = [
            TypefullyDraftResponse(
                draft_id="draft-1",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 18, 10, 5, tzinfo=timezone.utc),
                raw_response={"id": "draft-1"},
                dry_run=False,
            ),
            TypefullyDraftResponse(
                draft_id="draft-6",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 18, 10, 6, tzinfo=timezone.utc),
                raw_response={"id": "draft-6"},
                dry_run=False,
            ),
        ]
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True),
            settings=build_settings(),
        )
        service.export_service.publisher = publisher

        result = service.run(dry_run=False, limit=10)
        session.commit()

        assert result.phase == 3
        assert result.eligible_count == 2
        assert result.exported_count == 2
        assert result.capacity_deferred_count == 0
        assert result.failed_count == 0
        assert session.get(ContentCandidate, 1).external_publication_ref == "draft-1"
        assert session.get(ContentCandidate, 6).external_publication_ref == "draft-6"
        assert session.get(ContentCandidate, 5).external_publication_ref is None
        assert session.get(ContentCandidate, 7).external_publication_ref is None
        assert session.get(ContentCandidate, 8).external_publication_ref is None
    finally:
        session.close()


def test_typefully_autoexport_filters_by_published_date() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        candidate = session.get(ContentCandidate, 6)
        assert candidate is not None
        candidate.published_at = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)
        session.add(candidate)
        session.commit()

        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True),
            settings=build_settings(timezone="Europe/Madrid"),
        )

        result = service.run(dry_run=True, reference_date=date(2026, 3, 15), limit=10)

        assert {row.id for row in result.rows} == {1, 5}
    finally:
        session.close()


def test_typefully_autoexport_cli_status_reports_phase_and_last_run() -> None:
    runner = CliRunner()

    original_init_db = typefully_autoexport_pipeline.init_db
    original_session_scope = typefully_autoexport_pipeline.session_scope
    original_service = typefully_autoexport_pipeline.TypefullyAutoexportService
    try:
        class DummyService:
            def __init__(self, session) -> None:
                self.session = session

            def status(self) -> TypefullyAutoexportStatusView:
                return TypefullyAutoexportStatusView(
                    enabled=True,
                    phase=1,
                    max_exports_per_run=5,
                    max_exports_per_day=None,
                    stop_on_capacity_limit=True,
                    capacity_error_codes=["MONETIZATION_ERROR"],
                    allowed_content_types=[
                        ContentType.MATCH_RESULT,
                        ContentType.STANDINGS,
                        ContentType.PREVIEW,
                        ContentType.RANKING,
                    ],
                    validation_required_content_types=[],
                    manual_review_content_types=[],
                    pending_capacity_count=3,
                    pending_normal_count=4,
                    last_run=TypefullyAutoexportLastRun(
                        executed_at=datetime(2026, 3, 20, 10, 20, tzinfo=timezone.utc),
                        dry_run=False,
                        policy_enabled=True,
                        phase=1,
                        reference_date=date(2026, 3, 20),
                        scanned_count=12,
                        eligible_count=4,
                        exported_count=4,
                        blocked_count=2,
                        capacity_deferred_count=3,
                        failed_count=0,
                        capacity_limit_reached=True,
                        capacity_limit_reason="capacity_deferred:MONETIZATION_ERROR",
                    ),
                )

            def list_pending_capacity(self, **kwargs):
                return []

        @contextmanager
        def fake_session_scope():
            yield object()

        typefully_autoexport_pipeline.init_db = lambda: None
        typefully_autoexport_pipeline.session_scope = fake_session_scope
        typefully_autoexport_pipeline.TypefullyAutoexportService = DummyService

        result = runner.invoke(typefully_autoexport_pipeline.app, ["status"])

        assert result.exit_code == 0
        assert "enabled=true" in result.stdout
        assert "phase=1" in result.stdout
        assert "max_exports_per_run=5" in result.stdout
        assert "pending_capacity_count=3" in result.stdout
        assert "allowed_content_types=match_result, standings, preview, ranking" in result.stdout
        assert "last_execution=2026-03-20T10:20:00+00:00" in result.stdout
        assert "last_capacity_limit_reached=true" in result.stdout
        assert (
            "last_summary=AUTOEXPORT phase=1 scanned=12 eligible=4 exported=4 blocked=2 "
            "capacity_deferred=3 failed=0"
        ) in result.stdout
    finally:
        typefully_autoexport_pipeline.init_db = original_init_db
        typefully_autoexport_pipeline.session_scope = original_session_scope
        typefully_autoexport_pipeline.TypefullyAutoexportService = original_service


def test_typefully_autoexport_respects_max_exports_per_run() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        add_safe_candidate(session, 9)
        add_safe_candidate(session, 10)
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1).model_copy(update={"max_exports_per_run": 2}),
            settings=build_settings(),
        )
        publisher = Mock()
        publisher.export_text.side_effect = [
            TypefullyDraftResponse(
                draft_id="draft-1",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 18, 10, 5, tzinfo=timezone.utc),
                raw_response={"id": "draft-1"},
                dry_run=False,
            ),
            TypefullyDraftResponse(
                draft_id="draft-6",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 18, 10, 6, tzinfo=timezone.utc),
                raw_response={"id": "draft-6"},
                dry_run=False,
            ),
        ]
        service.export_service.publisher = publisher

        result = service.run(dry_run=False, limit=10)
        session.commit()

        assert result.exported_count == 2
        assert result.capacity_deferred_count == 2
        assert result.failed_count == 0
        assert result.capacity_limit_reached is True
        assert session.get(ContentCandidate, 9).external_publication_error == "capacity_deferred:max_exports_per_run"
        assert session.get(ContentCandidate, 10).external_publication_error == "capacity_deferred:max_exports_per_run"
    finally:
        session.close()


def test_typefully_autoexport_treats_monetization_error_as_capacity_limit() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        add_safe_candidate(session, 9)
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1).model_copy(update={"max_exports_per_run": 10}),
            settings=build_settings(),
        )
        publisher = Mock()
        publisher.export_text.side_effect = [
            TypefullyDraftResponse(
                draft_id="draft-1",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 18, 10, 5, tzinfo=timezone.utc),
                raw_response={"id": "draft-1"},
                dry_run=False,
            ),
            TypefullyApiError(
                "Typefully create draft failed with 402: {'code': 'MONETIZATION_ERROR'}",
                status_code=402,
                error_code="MONETIZATION_ERROR",
                detail="Please upgrade",
            ),
        ]
        service.export_service.publisher = publisher

        result = service.run(dry_run=False, limit=10)
        session.commit()

        assert result.exported_count == 1
        assert result.capacity_deferred_count == 2
        assert result.failed_count == 0
        assert result.capacity_limit_reason == "capacity_deferred:MONETIZATION_ERROR"
        assert session.get(ContentCandidate, 6).external_publication_error == "capacity_deferred:MONETIZATION_ERROR"
        assert session.get(ContentCandidate, 9).external_publication_error == "capacity_deferred:MONETIZATION_ERROR"
    finally:
        session.close()


def test_typefully_autoexport_retries_capacity_deferred_candidates_later() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        candidate = session.get(ContentCandidate, 1)
        assert candidate is not None
        candidate.external_publication_error = "capacity_deferred:MONETIZATION_ERROR"
        session.add(candidate)
        session.commit()

        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1),
            settings=build_settings(),
        )
        publisher = Mock()
        publisher.export_text.side_effect = [
            TypefullyDraftResponse(
                draft_id="draft-retry-1",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 19, 9, 0, tzinfo=timezone.utc),
                raw_response={"id": "draft-retry-1"},
                dry_run=False,
            ),
            TypefullyDraftResponse(
                draft_id="draft-retry-6",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 19, 9, 1, tzinfo=timezone.utc),
                raw_response={"id": "draft-retry-6"},
                dry_run=False,
            ),
        ]
        service.export_service.publisher = publisher

        result = service.run(dry_run=False, limit=10)
        session.commit()

        assert result.exported_count == 2
        assert result.capacity_deferred_count == 0
        assert session.get(ContentCandidate, 1).external_publication_ref == "draft-retry-1"
        assert session.get(ContentCandidate, 1).external_publication_error is None
    finally:
        session.close()


def test_typefully_autoexport_cli_pending_capacity_lists_deferred_rows() -> None:
    runner = CliRunner()

    original_init_db = typefully_autoexport_pipeline.init_db
    original_session_scope = typefully_autoexport_pipeline.session_scope
    original_service = typefully_autoexport_pipeline.TypefullyAutoexportService
    try:
        class DummyService:
            def __init__(self, session) -> None:
                self.session = session

            def status(self):
                raise AssertionError("status no debe llamarse en pending-capacity")

            def list_pending_capacity(self, **kwargs):
                return [
                    TypefullyAutoexportCandidateView(
                        id=42,
                        competition_slug="segunda_rfef_g3_baleares",
                        content_type=ContentType.MATCH_RESULT,
                        priority=97,
                        status=ContentCandidateStatus.PUBLISHED,
                        autoexport_allowed=True,
                        policy_reason="capacity_deferred:MONETIZATION_ERROR",
                        quality_check_passed=True,
                        quality_check_errors=[],
                        export_outcome="capacity_deferred",
                        has_rewrite=False,
                        text_source="text_draft",
                        external_publication_ref=None,
                        external_publication_error="capacity_deferred:MONETIZATION_ERROR",
                        excerpt="RESULTADO FINAL UE Porreres 0-1 Terrassa FC",
                    )
                ]

        @contextmanager
        def fake_session_scope():
            yield object()

        typefully_autoexport_pipeline.init_db = lambda: None
        typefully_autoexport_pipeline.session_scope = fake_session_scope
        typefully_autoexport_pipeline.TypefullyAutoexportService = DummyService

        result = runner.invoke(typefully_autoexport_pipeline.app, ["pending-capacity"])

        assert result.exit_code == 0
        assert "pending_capacity_count=1" in result.stdout
        assert "capacity_deferred:MONETIZATION_ERROR" in result.stdout
    finally:
        typefully_autoexport_pipeline.init_db = original_init_db
        typefully_autoexport_pipeline.session_scope = original_session_scope
        typefully_autoexport_pipeline.TypefullyAutoexportService = original_service
