from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import ContentCandidate
from app.services.editorial_rewrite_metrics import EditorialRewriteMetricsService
from tests.unit.services.test_editorial_rewriter import build_session, seed_candidates
from tests.unit.services.service_test_support import build_settings


def test_editorial_rewrite_metrics_report_daily_real_vs_fallback_ratio() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        session.add_all(
            [
                ContentCandidate(
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="preview",
                    priority=90,
                    text_draft="PREVIA",
                    payload_json={},
                    source_summary_hash="metrics-1",
                    status="approved",
                    rewritten_text="texto real",
                    rewrite_status="rewritten",
                    rewrite_model="openai/gpt-oss-20b",
                    rewrite_timestamp=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
                    rewrite_error=None,
                ),
                ContentCandidate(
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="viral_story",
                    priority=78,
                    text_draft="viral",
                    payload_json={},
                    source_summary_hash="metrics-2",
                    status="published",
                    rewritten_text="fallback",
                    rewrite_status="rewritten_fallback_base_text",
                    rewrite_model="openai/gpt-oss-20b",
                    rewrite_timestamp=datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc),
                    rewrite_error="rate limit reached",
                ),
                ContentCandidate(
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="viral_story",
                    priority=78,
                    text_draft="viral failed",
                    payload_json={},
                    source_summary_hash="metrics-3",
                    status="published",
                    rewritten_text=None,
                    rewrite_status="failed",
                    rewrite_model="openai/gpt-oss-20b",
                    rewrite_timestamp=datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc),
                    rewrite_error="timeout",
                ),
            ]
        )
        session.commit()

        report = EditorialRewriteMetricsService(session, settings=build_settings()).daily_outcome_report(
            start_date=datetime(2026, 3, 15, tzinfo=timezone.utc).date(),
            end_date=datetime(2026, 3, 16, tzinfo=timezone.utc).date(),
        )

        assert report["total_rewrites"] == 4
        assert report["real_count"] == 2
        assert report["fallback_count"] == 1
        assert report["failed_count"] == 1
        assert report["real_ratio"] == 0.5
        assert report["fallback_ratio"] == 0.25
        assert report["failed_ratio"] == 0.25
        assert report["by_content_type"]["preview"]["real"] == 2
        assert report["by_content_type"]["viral_story"]["fallback_base_text"] == 1
        assert report["by_content_type"]["viral_story"]["failed"] == 1
        assert len(report["days"]) == 2
        assert report["days"][0]["real_count"] == 2
        assert report["days"][0]["fallback_count"] == 1
        assert report["days"][1]["failed_count"] == 1
    finally:
        session.close()
