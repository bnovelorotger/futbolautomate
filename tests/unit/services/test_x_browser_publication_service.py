from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from app.channels.x_browser.schemas import XBrowserPublishResponse
from app.db.models import ContentCandidate
from app.services.telegram_publication_notifier import TelegramPublicationNotifier
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
            published_at=datetime(2026, 3, 15, 10, 5, tzinfo=UTC),
            dry_run=False,
        )
        publication_notifier = Mock(spec=TelegramPublicationNotifier)
        service = XBrowserPublicationService(
            session,
            publisher=publisher,
            scheduler=build_scheduler(current_time=datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))),
            publication_notifier=publication_notifier,
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
        publication_notifier.publication_succeeded.assert_called_once()
        publisher.publish_text.assert_called_once_with(
            "Torrent CF 1-0 UE Porreres. Final en Segunda RFEF balear.",
            image_path=None,
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


def test_x_browser_publication_service_publish_selected_pending_only_uses_requested_ids() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        now = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
        session.add(
            ContentCandidate(
                id=5,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="results_roundup",
                priority=98,
                text_draft="RESULTADO FINAL\n\nTorrent CF 2-0 UE Porreres",
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
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
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

        result = service.publish_selected_pending([5], limit=10, dry_run=True, stagger_seconds=0)

        assert result.published_count == 1
        assert [row.candidate_id for row in result.rows] == [5]
        publisher.publish_text.assert_called_once()
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
                published_at=datetime(2026, 3, 16, 9, 5, tzinfo=UTC),
                dry_run=False,
            ),
            XBrowserPublishResponse(
                text="SEGUNDO INTENTO",
                published_at=datetime(2026, 3, 16, 9, 6, tzinfo=UTC),
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


def _make_standings_candidate(tmp_path: Path, candidate_id: int = 42) -> tuple[ContentCandidate, Path]:
    now = datetime(2026, 3, 17, 10, 0, tzinfo=UTC)
    image_dir = tmp_path / "exports" / "images" / "tercera_rfef_g11" / "2026-03-17"
    image_dir.mkdir(parents=True)
    image_file = image_dir / f"standings_roundup_{candidate_id}.png"
    image_file.write_bytes(b"\x89PNG\r\n")
    candidate = ContentCandidate(
        id=candidate_id,
        competition_slug="tercera_rfef_g11",
        content_type="standings_roundup",
        priority=80,
        text_draft="Clasificación actualizada.",
        source_summary_hash=f"hash-{candidate_id}",
        status="published",
        created_at=now,
        updated_at=now,
    )
    return candidate, image_file


def test_find_image_for_candidate_returns_path_when_file_exists(tmp_path: Path) -> None:
    session = build_session()
    try:
        candidate, expected_image = _make_standings_candidate(tmp_path, candidate_id=42)

        from app.core.config import Settings

        settings = Settings(app_root=tmp_path)
        service = XBrowserPublicationService(session, settings=settings)

        result = service._find_image_for_candidate(candidate)

        assert result == expected_image
    finally:
        session.close()


def test_publish_standings_thread_falls_back_when_single_candidate() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.publish_text.return_value = XBrowserPublishResponse(
            text="Clasificación actualizada.",
            published_at=datetime(2026, 3, 16, 10, 5, tzinfo=UTC),
            dry_run=False,
        )
        service = XBrowserPublicationService(
            session,
            publisher=publisher,
            scheduler=build_scheduler(current_time=datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))),
        )

        result = service.publish_standings_thread(dry_run=False)

        # Only one standings_roundup candidate exists — falls back to publish_pending
        # which publishes all pending candidates individually via publish_text
        publisher.publish_thread.assert_not_called()
        assert result is not None
    finally:
        session.close()


def test_list_all_unpublished_ignores_window() -> None:
    """Candidates published 5 days ago (outside the 96h rescue window) still appear in list_all_unpublished."""
    session = build_session()
    try:
        seed_candidates(session)
        five_days_ago = datetime(2026, 3, 11, 10, 0, tzinfo=UTC)
        session.add(
            ContentCandidate(
                id=10,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="results_roundup",
                priority=85,
                text_draft="RESULTADO ANTIGUO",
                payload_json=build_results_payload(
                    reference_date="2026-03-11",
                    match_date="2026-03-10",
                ),
                source_summary_hash="hash-10",
                status="published",
                reviewed_at=five_days_ago,
                approved_at=five_days_ago,
                published_at=five_days_ago,
                external_publication_ref=None,
                created_at=five_days_ago,
                updated_at=five_days_ago,
            )
        )
        session.commit()

        # current_time is 5 days after the candidate's published_at — outside the 96h rescue window
        current_time = datetime(2026, 3, 16, 10, 0, tzinfo=UTC)
        service = XBrowserPublicationService(
            session,
            scheduler=build_scheduler(current_time=current_time),
        )

        all_unpublished = service.list_all_unpublished(limit=100)
        pending = service.list_pending(limit=100)

        all_ids = [row.id for row in all_unpublished]
        pending_ids = [row.id for row in pending]

        assert 10 in all_ids, "Stranded candidate must appear in list_all_unpublished"
        assert 10 not in pending_ids, "Stranded candidate must NOT appear in list_pending (outside 96h window)"
    finally:
        session.close()


def test_publish_pending_bypass_schedule_rescues_3day_old_stranded_candidate() -> None:
    """A candidate published 3 days ago (72h, within 96h rescue window) must be rescued by bypass_schedule=True."""
    session = build_session()
    try:
        three_days_ago = datetime(2026, 3, 13, 10, 0, tzinfo=UTC)
        current_time = datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        session.add(
            ContentCandidate(
                id=60,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="results_roundup",
                priority=99,
                text_draft="RESULTADO VARADO TRES DIAS",
                payload_json=build_results_payload(reference_date="2026-03-13", match_date="2026-03-12"),
                source_summary_hash="hash-60",
                status="published",
                published_at=three_days_ago,
                created_at=three_days_ago,
                updated_at=three_days_ago,
            )
        )
        session.commit()

        publisher = Mock()
        publisher.publish_text.return_value = XBrowserPublishResponse(
            text="RESULTADO VARADO TRES DIAS",
            published_at=datetime(2026, 3, 16, 10, 5, tzinfo=UTC),
            dry_run=False,
        )
        window_service = Mock()
        window_service.matches_release_window.return_value = False
        service = XBrowserPublicationService(
            session,
            publisher=publisher,
            scheduler=build_scheduler(current_time=current_time),
            window_service=window_service,
        )

        normal_result = service.publish_pending(limit=10, dry_run=True, stagger_seconds=0)
        bypass_result = service.publish_pending(limit=10, dry_run=True, stagger_seconds=0, bypass_schedule=True)

        normal_ids = [r.candidate_id for r in normal_result.rows]
        bypass_ids = [r.candidate_id for r in bypass_result.rows]
        assert 60 not in normal_ids, "3-day-old candidate must not appear in normal pending"
        assert 60 in bypass_ids, "3-day-old candidate within 96h window must be rescued by bypass"
    finally:
        session.close()


def test_publish_pending_bypass_schedule_publishes_on_non_scheduled_day() -> None:
    """bypass_schedule=True must publish results_roundup on a Saturday (not in publication_schedule)."""
    session = build_session()
    try:
        # Saturday 2026-03-14 — not in publication_schedule (only Monday is for results_roundup)
        saturday = datetime(2026, 3, 14, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        # Candidate published yesterday (Friday), scheduled_at also in the past → no future-schedule block
        friday = datetime(2026, 3, 13, 10, 0, tzinfo=UTC)
        session.add(
            ContentCandidate(
                id=50,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="results_roundup",
                priority=99,
                text_draft="RESULTADO DEL VIERNES",
                payload_json=build_results_payload(reference_date="2026-03-13", match_date="2026-03-13"),
                source_summary_hash="hash-50",
                scheduled_at=friday,
                status="published",
                published_at=friday,
                created_at=friday,
                updated_at=friday,
            )
        )
        session.commit()

        publisher = Mock()
        publisher.publish_text.return_value = XBrowserPublishResponse(
            text="RESULTADO DEL VIERNES",
            published_at=datetime(2026, 3, 14, 10, 5, tzinfo=UTC),
            dry_run=False,
        )
        window_service = Mock()
        window_service.matches_release_window.return_value = True
        service = XBrowserPublicationService(
            session,
            publisher=publisher,
            scheduler=build_scheduler(current_time=saturday),
            window_service=window_service,
        )

        normal_result = service.publish_pending(limit=10, dry_run=True, stagger_seconds=0)
        bypass_result = service.publish_pending(limit=10, dry_run=True, stagger_seconds=0, bypass_schedule=True)

        assert normal_result.published_count == 0, "Saturday must yield 0 without bypass"
        assert bypass_result.published_count >= 1, "bypass_schedule=True must publish despite Saturday"
        assert any(r.candidate_id == 50 for r in bypass_result.rows)
    finally:
        session.close()


def test_publish_pending_bypass_schedule_excludes_future_scheduled() -> None:
    """bypass_schedule=True must not publish candidates whose scheduled_at is in the future."""
    session = build_session()
    try:
        now = datetime(2026, 3, 14, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        future_time = datetime(2026, 3, 15, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        session.add_all(
            [
                ContentCandidate(
                    id=20,
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="results_roundup",
                    priority=99,
                    text_draft="PASADO — sin scheduled_at",
                    payload_json=build_results_payload(reference_date="2026-03-14", match_date="2026-03-13"),
                    source_summary_hash="hash-20",
                    status="published",
                    published_at=now,
                    created_at=now,
                    updated_at=now,
                ),
                ContentCandidate(
                    id=21,
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="results_roundup",
                    priority=98,
                    text_draft="FUTURO — scheduled_at mañana",
                    payload_json=build_results_payload(reference_date="2026-03-15", match_date="2026-03-14"),
                    source_summary_hash="hash-21",
                    scheduled_at=future_time,
                    status="published",
                    published_at=now,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()

        service = XBrowserPublicationService(
            session,
            publisher=Mock(),
            scheduler=build_scheduler(current_time=now),
        )

        result = service.publish_pending(limit=10, dry_run=True, stagger_seconds=0, bypass_schedule=True)

        published_ids = [row.candidate_id for row in result.rows]
        assert 20 in published_ids, "Past candidate (no scheduled_at) must be included"
        assert 21 not in published_ids, "Future scheduled_at must be excluded even with bypass"
    finally:
        session.close()


def test_publish_pending_bypass_schedule_enforces_minimum_stagger() -> None:
    """bypass_schedule=True enforces at least 900s stagger regardless of the explicit value."""
    from unittest.mock import patch

    session = build_session()
    try:
        now = datetime(2026, 3, 14, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        for i, cid in enumerate([30, 31]):
            session.add(
                ContentCandidate(
                    id=cid,
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="results_roundup",
                    priority=99 - i,
                    text_draft=f"POST {cid}",
                    payload_json=build_results_payload(reference_date="2026-03-14", match_date="2026-03-13"),
                    source_summary_hash=f"hash-{cid}",
                    status="published",
                    published_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()

        publisher = Mock()
        publisher.publish_text.return_value = XBrowserPublishResponse(
            text="POST",
            published_at=datetime(2026, 3, 14, 10, 5, tzinfo=UTC),
            dry_run=False,
        )
        service = XBrowserPublicationService(
            session,
            publisher=publisher,
            scheduler=build_scheduler(current_time=now),
        )

        with patch("app.services.x_browser_publication_service.time") as mock_time:
            service.publish_pending(limit=10, dry_run=False, stagger_seconds=0, bypass_schedule=True)
            # Must have slept for at least 900s between the two posts
            sleep_calls = [call.args[0] for call in mock_time.sleep.call_args_list]
            assert any(s >= 900 for s in sleep_calls), f"Expected sleep ≥900s; got {sleep_calls}"
    finally:
        session.close()


def test_find_image_for_candidate_returns_none_when_file_missing(tmp_path: Path) -> None:
    session = build_session()
    try:
        candidate = ContentCandidate(
            id=99,
            competition_slug="tercera_rfef_g11",
            content_type="standings_roundup",
            priority=80,
            text_draft="Clasificación.",
            source_summary_hash="hash-99",
            status="published",
        )

        from app.core.config import Settings

        settings = Settings(app_root=tmp_path)
        service = XBrowserPublicationService(session, settings=settings)

        result = service._find_image_for_candidate(candidate)

        assert result is None
    finally:
        session.close()
