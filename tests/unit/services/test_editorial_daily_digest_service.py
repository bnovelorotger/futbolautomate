from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.db.models import ContentCandidate
from app.services.editorial_daily_digest_service import EditorialDailyDigestService
from tests.unit.services.service_test_support import build_session, build_settings


def _candidate(
    *,
    candidate_id: int,
    content_type: str,
    status: str,
    created_at: datetime,
    published_at: datetime | None = None,
    rejection_reason: str | None = None,
    quality_check_errors: list[str] | None = None,
    external_publication_ref: str | None = None,
    external_publication_error: str | None = None,
    rewrite_status: str | None = None,
    rewrite_timestamp: datetime | None = None,
) -> ContentCandidate:
    return ContentCandidate(
        id=candidate_id,
        competition_slug="tercera_rfef_g11",
        content_type=content_type,
        priority=80,
        text_draft="texto",
        formatted_text="texto",
        payload_json={"content_key": f"{content_type}:{candidate_id}", "source_payload": {}},
        source_summary_hash=f"hash-{candidate_id}",
        scheduled_at=created_at,
        status=status,
        rewritten_text=None,
        rewrite_status=rewrite_status,
        rewrite_model="groq" if rewrite_status else None,
        rewrite_timestamp=rewrite_timestamp,
        rewrite_error=None,
        reviewed_at=created_at if status in {"approved", "published", "rejected"} else None,
        approved_at=created_at if status == "published" else None,
        autoapproved=None,
        autoapproved_at=None,
        autoapproval_reason=None,
        published_at=published_at,
        rejection_reason=rejection_reason,
        external_publication_ref=external_publication_ref,
        external_channel="x" if external_publication_ref else None,
        external_exported_at=published_at if external_publication_ref else None,
        external_publication_timestamp=published_at if external_publication_ref else None,
        external_publication_attempted_at=published_at,
        external_publication_error=external_publication_error,
        publication_attempts=1 if published_at else 0,
        quality_check_passed=quality_check_errors is None,
        quality_check_errors=quality_check_errors,
        quality_checked_at=created_at,
        created_at=created_at,
        updated_at=created_at,
    )


def test_editorial_daily_digest_service_builds_report_and_renders_outputs() -> None:
    session = build_session()
    try:
        now = datetime(2026, 5, 18, 20, 0, tzinfo=UTC)
        session.add_all(
            [
                _candidate(
                    candidate_id=1,
                    content_type="preview",
                    status="draft",
                    created_at=now - timedelta(hours=4),
                    quality_check_errors=["preview_missing_match"],
                ),
                _candidate(
                    candidate_id=2,
                    content_type="viral_story",
                    status="rejected",
                    created_at=now - timedelta(hours=3),
                    rejection_reason="quality_check_failed",
                    quality_check_errors=["rewrite_ai_cliche:en_resumen"],
                ),
                _candidate(
                    candidate_id=3,
                    content_type="preview",
                    status="published",
                    created_at=now - timedelta(hours=2),
                    published_at=now - timedelta(hours=2),
                    external_publication_ref="x-browser:123",
                    rewrite_status="rewritten",
                    rewrite_timestamp=now - timedelta(hours=2),
                ),
                _candidate(
                    candidate_id=4,
                    content_type="viral_story",
                    status="published",
                    created_at=now - timedelta(hours=1),
                    published_at=now - timedelta(hours=1),
                    external_publication_error="browser timeout",
                    rewrite_status="rewritten_fallback_base_text",
                    rewrite_timestamp=now - timedelta(hours=1),
                ),
                _candidate(
                    candidate_id=5,
                    content_type="preview",
                    status="published",
                    created_at=now - timedelta(minutes=30),
                    published_at=now - timedelta(minutes=30),
                    rewrite_status="failed",
                    rewrite_timestamp=now - timedelta(minutes=30),
                ),
            ]
        )
        session.commit()

        service = EditorialDailyDigestService(
            session,
            settings=build_settings(timezone="Europe/Madrid"),
        )
        report = service.build_report(reference_date=date(2026, 5, 18), window_days=1)

        assert report.publication.published_to_x == 1
        assert report.publication.pending_dispatch == 1
        assert report.publication.publication_errors == 1
        assert report.queue.draft_count == 1
        assert report.queue.rejected_count == 1
        assert report.queue.top_rejection_reasons[0].code == "quality_check_failed"
        assert report.queue.top_quality_errors[0].code in {
            "preview_missing_match",
            "rewrite_ai_cliche:en_resumen",
        }
        assert report.rewrite.total_rewrites == 3
        assert report.rewrite.real_count == 1
        assert report.rewrite.fallback_count == 1
        assert report.rewrite.failed_count == 1
        assert report.rewrite.real_ratio == 0.3333
        assert report.has_alerts is True

        console_output = service.render_console(report)
        telegram_output = service.render_telegram(report)

        assert "futbolbalear - cierre diario 2026-05-18" in console_output
        assert "Publicacion" in console_output
        assert "- publicados en X: 1" in console_output
        assert "Rewrite fase 3" in console_output
        assert "fallback" in telegram_output
        assert "quality top:" in telegram_output
        assert "Alertas" in telegram_output
    finally:
        session.close()
