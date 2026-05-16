from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from app.channels.x_browser.schemas import XBrowserPublishResponse
from app.db.models import ContentCandidate
from app.services.x_browser_publication_service import XBrowserPublicationService
from tests.unit.services.test_x_publication_service import (
    build_preview_payload,
    build_results_payload,
    build_scheduler,
    build_session,
    seed_candidates,
)


def test_x_browser_publication_service_lists_and_publishes_with_x_channel() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.publish_text.return_value = XBrowserPublishResponse(
            text="RESULTADO FINAL",
            published_at=datetime(2026, 3, 15, 10, 5, tzinfo=timezone.utc),
            dry_run=False,
        )
        service = XBrowserPublicationService(
            session,
            publisher=publisher,
            scheduler=build_scheduler(current_time=datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))),
        )

        pending = service.list_pending(limit=10)
        result = service.publish_candidate(1, dry_run=False)
        session.commit()

        candidate = session.get(ContentCandidate, 1)
        assert [row.id for row in pending] == [1]
        assert pending[0].selected_text_source == "rewritten_text"
        assert result.candidate.external_publication_ref is not None
        assert result.candidate.external_publication_ref.startswith("x-browser:")
        assert candidate is not None
        assert candidate.external_channel == "x"
        assert candidate.external_publication_ref is not None
        assert candidate.external_publication_ref.startswith("x-browser:")
        assert candidate.external_publication_error is None
        publisher.publish_text.assert_called_once_with(
            "Torrent CF 1-0 UE Porreres. Final en Segunda RFEF balear.",
            dry_run=False,
        )
    finally:
        session.close()


def test_x_browser_publication_service_publish_pending_dry_run_does_not_persist_attempts() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.publish_text.return_value = XBrowserPublishResponse(
            text="RESULTADO FINAL",
            dry_run=True,
        )
        service = XBrowserPublicationService(
            session,
            publisher=publisher,
            scheduler=build_scheduler(current_time=datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))),
        )

        result = service.publish_pending(limit=10, dry_run=True, stagger_seconds=0)
        session.commit()

        candidate = session.get(ContentCandidate, 1)
        assert result.dry_run is True
        assert result.published_count == 1
        assert [row.candidate_id for row in result.rows] == [1]
        assert candidate is not None
        assert candidate.external_publication_ref is None
        assert candidate.external_publication_attempted_at is None
        assert candidate.publication_attempts == 0
    finally:
        session.close()


def test_x_browser_publication_service_publish_pending_respects_schedule_and_retry_budget() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        now = datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        session.add_all(
            [
                ContentCandidate(
                    id=5,
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="results_roundup",
                    priority=95,
                    text_draft="SEGUNDO INTENTO",
                    payload_json=build_results_payload(
                        reference_date="2026-03-16",
                        match_date="2026-03-15",
                    ),
                    source_summary_hash="hash-5",
                    scheduled_at=now,
                    status="published",
                    reviewed_at=now,
                    approved_at=now,
                    published_at=now,
                    external_publication_error="rate limit",
                    publication_attempts=2,
                    created_at=now,
                    updated_at=now,
                ),
                ContentCandidate(
                    id=6,
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="results_roundup",
                    priority=94,
                    text_draft="NO MAS RETRIES",
                    payload_json=build_results_payload(
                        reference_date="2026-03-16",
                        match_date="2026-03-15",
                    ),
                    source_summary_hash="hash-6",
                    scheduled_at=now,
                    status="published",
                    reviewed_at=now,
                    approved_at=now,
                    published_at=now,
                    external_publication_error="rate limit",
                    publication_attempts=3,
                    created_at=now,
                    updated_at=now,
                ),
                ContentCandidate(
                    id=7,
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="featured_match_preview",
                    priority=93,
                    text_draft="VIERNES SOLO",
                    payload_json=build_preview_payload(
                        reference_date="2026-03-20",
                        match_date="2026-03-20",
                    ),
                    source_summary_hash="hash-7",
                    scheduled_at=now,
                    status="published",
                    reviewed_at=now,
                    approved_at=now,
                    published_at=now,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()

        publisher = Mock()
        publisher.publish_text.side_effect = [
            XBrowserPublishResponse(
                text="RESULTADO FINAL",
                published_at=datetime(2026, 3, 16, 9, 5, tzinfo=timezone.utc),
                dry_run=False,
            ),
            XBrowserPublishResponse(
                text="SEGUNDO INTENTO",
                published_at=datetime(2026, 3, 16, 9, 6, tzinfo=timezone.utc),
                dry_run=False,
            ),
        ]
        service = XBrowserPublicationService(
            session,
            publisher=publisher,
            scheduler=build_scheduler(current_time=now),
        )

        result = service.publish_pending(limit=10, dry_run=False, stagger_seconds=0)
        session.commit()

        candidate_1 = session.get(ContentCandidate, 1)
        candidate_5 = session.get(ContentCandidate, 5)
        candidate_6 = session.get(ContentCandidate, 6)
        candidate_7 = session.get(ContentCandidate, 7)

        assert [row.candidate_id for row in result.rows] == [1, 5]
        assert result.published_count == 2
        assert candidate_1 is not None
        assert candidate_1.external_channel == "x"
        assert candidate_5 is not None
        assert candidate_5.external_publication_ref is not None
        assert candidate_5.external_publication_ref.startswith("x-browser:")
        assert candidate_5.external_channel == "x"
        assert candidate_5.publication_attempts == 3
        assert candidate_6 is not None
        assert candidate_6.external_publication_ref is None
        assert candidate_6.publication_attempts == 3
        assert candidate_7 is not None
        assert candidate_7.external_publication_ref is None
    finally:
        session.close()
