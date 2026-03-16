from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from app.channels.typefully.client import TypefullyApiError, TypefullyConfigurationError
from app.channels.typefully.schemas import TypefullyDraftResponse
from app.core.config import Settings
from app.core.exceptions import InvalidStateTransitionError
from app.db.base import Base
from app.db.models import Competition, ContentCandidate
from app.pipelines import typefully_export as typefully_export_pipeline
from app.services.typefully_export_service import (
    TypefullyExportService,
    is_candidate_eligible_for_typefully,
)


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def build_settings(**overrides) -> Settings:
    payload = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "typefully_api_key": "typefully-api-key",
        "typefully_api_url": "https://api.typefully.com",
    }
    payload.update(overrides)
    return Settings(**payload)


def seed_candidates(session: Session) -> None:
    now = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    competition = Competition(
        code="segunda_rfef_g3_baleares",
        name="2a RFEF Grupo 3",
        normalized_name="2a rfef grupo 3",
        category_level=4,
        gender="male",
        region="Baleares",
        country="Spain",
        federation="RFEF",
        source_name="futbolme",
        source_competition_id="3059",
    )
    session.add(competition)
    session.flush()
    session.add_all(
        [
            ContentCandidate(
                id=1,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="match_result",
                priority=99,
                text_draft="RESULTADO FINAL\n\nTorrent CF 1-0 UE Porreres",
                rewritten_text="Torrent CF se impuso por 1-0 a la UE Porreres.",
                rewrite_status="rewritten",
                rewrite_model="gpt-4.1-mini",
                rewrite_timestamp=now,
                rewrite_error=None,
                payload_json={},
                source_summary_hash="hash-1",
                scheduled_at=now,
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
                id=2,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="standings",
                priority=80,
                text_draft="CLASIFICACION\n\n1. UE Sant Andreu - 54 pts",
                rewritten_text=None,
                rewrite_status=None,
                rewrite_model=None,
                rewrite_timestamp=None,
                rewrite_error=None,
                payload_json={},
                source_summary_hash="hash-2",
                scheduled_at=now,
                status="published",
                reviewed_at=now,
                approved_at=now,
                published_at=now,
                rejection_reason=None,
                external_publication_ref="draft-2",
                external_channel="typefully",
                external_exported_at=now,
                external_publication_timestamp=None,
                external_publication_attempted_at=now,
                external_publication_error=None,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=3,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="preview",
                priority=90,
                text_draft="PREVIA",
                rewritten_text=None,
                rewrite_status=None,
                rewrite_model=None,
                rewrite_timestamp=None,
                rewrite_error=None,
                payload_json={},
                source_summary_hash="hash-3",
                scheduled_at=now,
                status="approved",
                reviewed_at=now,
                approved_at=now,
                published_at=None,
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
                id=4,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="ranking",
                priority=70,
                text_draft="   ",
                rewritten_text=None,
                rewrite_status=None,
                rewrite_model=None,
                rewrite_timestamp=None,
                rewrite_error=None,
                payload_json={},
                source_summary_hash="hash-4",
                scheduled_at=now,
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
                id=5,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="stat_narrative",
                priority=65,
                text_draft="NARRATIVA ESTADISTICA\n\nDato base",
                rewritten_text=None,
                rewrite_status=None,
                rewrite_model=None,
                rewrite_timestamp=None,
                rewrite_error=None,
                payload_json={},
                source_summary_hash="hash-5",
                scheduled_at=now,
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
                id=6,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="preview",
                priority=64,
                text_draft="PREVIA BASE\n\nTexto original",
                rewritten_text="   ",
                rewrite_status="rewritten",
                rewrite_model="gpt-4.1-mini",
                rewrite_timestamp=now,
                rewrite_error=None,
                payload_json={},
                source_summary_hash="hash-6",
                scheduled_at=now,
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


def test_typefully_export_service_eligibility_filter() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        candidate_1 = session.get(ContentCandidate, 1)
        candidate_2 = session.get(ContentCandidate, 2)
        candidate_3 = session.get(ContentCandidate, 3)
        candidate_4 = session.get(ContentCandidate, 4)
        candidate_5 = session.get(ContentCandidate, 5)
        candidate_6 = session.get(ContentCandidate, 6)

        assert candidate_1 is not None
        assert candidate_2 is not None
        assert candidate_3 is not None
        assert candidate_4 is not None
        assert candidate_5 is not None
        assert candidate_6 is not None
        assert is_candidate_eligible_for_typefully(candidate_1) is True
        assert is_candidate_eligible_for_typefully(candidate_2) is False
        assert is_candidate_eligible_for_typefully(candidate_3) is False
        assert is_candidate_eligible_for_typefully(candidate_4) is False
        assert is_candidate_eligible_for_typefully(candidate_5) is True
        assert is_candidate_eligible_for_typefully(candidate_6) is True
    finally:
        session.close()


def test_typefully_export_service_lists_and_exports_with_rewrite_by_default() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.export_text.return_value = TypefullyDraftResponse(
            draft_id="draft-1",
            social_set_id="social-set-1",
            exported_at=datetime(2026, 3, 15, 10, 5, tzinfo=timezone.utc),
            raw_response={"id": "draft-1"},
            dry_run=False,
        )
        service = TypefullyExportService(
            session,
            publisher=publisher,
            settings=build_settings(),
        )

        pending = service.list_pending(limit=10)
        result = service.export_candidate(1, dry_run=False)
        session.commit()

        assert [row.id for row in pending] == [1, 5, 6]
        assert pending[0].has_rewrite is True
        assert pending[0].text_source == "rewritten_text"
        assert result.candidate.external_publication_ref == "draft-1"
        assert result.candidate.external_channel == "typefully"
        assert result.candidate.external_exported_at is not None
        assert result.candidate.external_publication_error is None
        assert result.candidate.text_source == "rewritten_text"
        assert session.get(ContentCandidate, 1).external_publication_ref == "draft-1"
        assert session.get(ContentCandidate, 1).external_channel == "typefully"
        publisher.export_text.assert_called_once_with(
            "Torrent CF se impuso por 1-0 a la UE Porreres.",
            dry_run=False,
        )
    finally:
        session.close()


def test_typefully_export_service_can_force_original_draft() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.export_text.return_value = TypefullyDraftResponse(
            draft_id="draft-1",
            social_set_id="social-set-1",
            exported_at=datetime(2026, 3, 15, 10, 5, tzinfo=timezone.utc),
            raw_response={"id": "draft-1"},
            dry_run=False,
        )
        service = TypefullyExportService(session, publisher=publisher, settings=build_settings())

        result = service.export_candidate(1, dry_run=False, prefer_rewrite=False)

        assert result.candidate.text_source == "text_draft"
        publisher.export_text.assert_called_once_with(
            "RESULTADO FINAL\n\nTorrent CF 1-0 UE Porreres",
            dry_run=False,
        )
    finally:
        session.close()


def test_typefully_export_service_falls_back_to_draft_when_rewrite_is_empty() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.export_text.return_value = TypefullyDraftResponse(
            draft_id="draft-6",
            social_set_id="social-set-1",
            exported_at=datetime(2026, 3, 15, 10, 5, tzinfo=timezone.utc),
            raw_response={"id": "draft-6"},
            dry_run=False,
        )
        service = TypefullyExportService(session, publisher=publisher, settings=build_settings())

        pending = service.list_pending(limit=10)
        result = service.export_candidate(6, dry_run=False)

        row = next(row for row in pending if row.id == 6)
        assert row.has_rewrite is False
        assert row.text_source == "text_draft"
        assert result.candidate.text_source == "text_draft"
        publisher.export_text.assert_called_once_with(
            "PREVIA BASE\n\nTexto original",
            dry_run=False,
        )
    finally:
        session.close()


def test_typefully_export_service_records_api_error_without_ref() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.export_text.side_effect = TypefullyApiError("rate limit")
        service = TypefullyExportService(
            session,
            publisher=publisher,
            settings=build_settings(),
        )

        with pytest.raises(TypefullyApiError):
            service.export_candidate(1, dry_run=False)
        session.commit()

        candidate = session.get(ContentCandidate, 1)
        assert candidate.external_publication_ref is None
        assert candidate.external_publication_attempted_at is not None
        assert candidate.external_publication_error == "rate limit"
    finally:
        session.close()


def test_typefully_export_service_supports_dry_run_without_persistence() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.export_text.return_value = TypefullyDraftResponse(
            draft_id="dry-run",
            social_set_id="dry-run",
            exported_at=datetime(2026, 3, 15, 10, 5, tzinfo=timezone.utc),
            raw_response={"dry_run": True},
            dry_run=True,
        )
        service = TypefullyExportService(
            session,
            publisher=publisher,
            settings=build_settings(),
        )

        result = service.export_candidate(5, dry_run=True)
        session.commit()

        candidate = session.get(ContentCandidate, 5)
        assert result.dry_run is True
        assert result.candidate.text_source == "text_draft"
        assert candidate.external_publication_ref is None
        assert candidate.external_publication_attempted_at is None
    finally:
        session.close()


def test_typefully_export_service_export_ready_dry_run() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.export_text.return_value = TypefullyDraftResponse(
            draft_id="dry-run",
            social_set_id="dry-run",
            exported_at=datetime(2026, 3, 15, 10, 5, tzinfo=timezone.utc),
            raw_response={"dry_run": True},
            dry_run=True,
        )
        service = TypefullyExportService(
            session,
            publisher=publisher,
            settings=build_settings(),
        )

        result = service.export_ready(limit=10, dry_run=True)
        session.commit()

        assert result.dry_run is True
        assert result.exported_count == 3
        assert [row.id for row in result.rows] == [1, 5, 6]
        assert session.get(ContentCandidate, 1).external_publication_ref is None
    finally:
        session.close()


def test_typefully_export_service_rejects_invalid_states_and_config_errors() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.export_text.side_effect = TypefullyConfigurationError("falta TYPEFULLY_API_KEY")
        service = TypefullyExportService(
            session,
            publisher=publisher,
            settings=build_settings(),
        )

        with pytest.raises(InvalidStateTransitionError):
            service.export_candidate(3, dry_run=False)

        with pytest.raises(InvalidStateTransitionError):
            service.export_candidate(2, dry_run=False)

        with pytest.raises(InvalidStateTransitionError):
            service.export_candidate(4, dry_run=False)

        with pytest.raises(TypefullyConfigurationError):
            service.export_candidate(1, dry_run=False)
        assert session.get(ContentCandidate, 1).external_publication_attempted_at is not None
        assert session.get(ContentCandidate, 1).external_publication_error == "falta TYPEFULLY_API_KEY"
    finally:
        session.close()


def test_typefully_export_service_reports_verify_config_without_touching_secrets() -> None:
    status = TypefullyExportService.config_status(build_settings(typefully_social_set_id="social-set-1"))

    assert status.ready is True
    assert status.has_api_key is True
    assert status.has_api_url is True
    assert status.api_url == "https://api.typefully.com"
    assert status.social_set_id == "social-set-1"
    assert status.social_set_strategy == "env"


def test_typefully_export_cli_flags_are_forwarded() -> None:
    runner = CliRunner()
    calls: list[bool] = []

    class FakeService:
        def __init__(self, session) -> None:
            self.session = session

        def export_candidate(self, candidate_id: int, *, dry_run: bool, prefer_rewrite: bool):
            calls.append(prefer_rewrite)
            return {
                "candidate_id": candidate_id,
                "dry_run": dry_run,
                "prefer_rewrite": prefer_rewrite,
            }

    @contextmanager
    def fake_session_scope():
        yield object()

    def fake_render(payload) -> str:
        return f"prefer_rewrite={payload['prefer_rewrite']}"

    original_service = typefully_export_pipeline.TypefullyExportService
    original_session_scope = typefully_export_pipeline.session_scope
    original_init_db = typefully_export_pipeline.init_db
    original_render = typefully_export_pipeline.render_typefully_result
    try:
        typefully_export_pipeline.TypefullyExportService = FakeService
        typefully_export_pipeline.session_scope = fake_session_scope
        typefully_export_pipeline.init_db = lambda: None
        typefully_export_pipeline.render_typefully_result = fake_render

        result_rewrite = runner.invoke(typefully_export_pipeline.app, ["export", "--id", "19", "--use-rewrite"])
        result_draft = runner.invoke(typefully_export_pipeline.app, ["export", "--id", "19", "--use-draft"])

        assert result_rewrite.exit_code == 0
        assert result_draft.exit_code == 0
        assert "prefer_rewrite=True" in result_rewrite.stdout
        assert "prefer_rewrite=False" in result_draft.stdout
        assert calls == [True, False]
    finally:
        typefully_export_pipeline.TypefullyExportService = original_service
        typefully_export_pipeline.session_scope = original_session_scope
        typefully_export_pipeline.init_db = original_init_db
        typefully_export_pipeline.render_typefully_result = original_render
