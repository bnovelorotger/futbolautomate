from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import ContentCandidate
from app.services.x_publication_scheduler import XPublicationScheduler
from tests.unit.services.service_test_support import build_settings


def build_candidate(
    *,
    candidate_id: int,
    content_type: str,
    external_publication_error: str | None = None,
    publication_attempts: int = 0,
) -> ContentCandidate:
    now = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    return ContentCandidate(
        id=candidate_id,
        competition_slug="segunda_rfef_g3_baleares",
        content_type=content_type,
        priority=10,
        text_draft="Texto listo para X",
        payload_json={},
        source_summary_hash=f"hash-{candidate_id}",
        scheduled_at=now,
        status="published",
        published_at=now,
        external_publication_error=external_publication_error,
        publication_attempts=publication_attempts,
        created_at=now,
        updated_at=now,
    )


def test_scheduler_filters_by_day_hour_and_type() -> None:
    scheduler = XPublicationScheduler(
        settings=build_settings(timezone="Europe/Madrid"),
        now_provider=lambda: datetime(2026, 3, 16, 10, 0),
    )
    monday_roundup = build_candidate(candidate_id=1, content_type="results_roundup")
    monday_top_scorer = build_candidate(candidate_id=2, content_type="top_scorer_update")
    monday_preview = build_candidate(candidate_id=3, content_type="featured_match_preview")
    monday_race = build_candidate(candidate_id=4, content_type="race_narrative")
    monday_milestone = build_candidate(candidate_id=5, content_type="milestone_story")

    publishable = scheduler.filter_candidates(
        [monday_roundup, monday_top_scorer, monday_preview, monday_race, monday_milestone]
    )

    assert [candidate.id for candidate in publishable] == [1, 2, 4]


def test_scheduler_enforces_retry_budget() -> None:
    scheduler = XPublicationScheduler(
        settings=build_settings(timezone="Europe/Madrid"),
        now_provider=lambda: datetime(2026, 3, 16, 10, 0),
    )
    retryable = build_candidate(
        candidate_id=1,
        content_type="results_roundup",
        external_publication_error="rate limit",
        publication_attempts=2,
    )
    exhausted = build_candidate(
        candidate_id=2,
        content_type="results_roundup",
        external_publication_error="rate limit",
        publication_attempts=3,
    )

    assert scheduler.is_candidate_publishable(retryable) is True
    assert scheduler.is_candidate_publishable(exhausted) is False
