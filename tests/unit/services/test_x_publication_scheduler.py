from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

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
    now = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
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

    assert [candidate.id for candidate in publishable] == [1, 2, 4, 5]


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


def test_scheduler_allows_tuesday_rankings_and_thursday_top_scorer() -> None:
    tuesday_scheduler = XPublicationScheduler(
        settings=build_settings(timezone="Europe/Madrid"),
        now_provider=lambda: datetime(2026, 3, 17, 20, 0),
    )
    thursday_scheduler = XPublicationScheduler(
        settings=build_settings(timezone="Europe/Madrid"),
        now_provider=lambda: datetime(2026, 3, 19, 20, 0),
    )
    saturday_scheduler = XPublicationScheduler(
        settings=build_settings(timezone="Europe/Madrid"),
        now_provider=lambda: datetime(2026, 3, 21, 11, 0),
    )

    ranking = build_candidate(candidate_id=10, content_type="ranking")
    top_scorer = build_candidate(candidate_id=11, content_type="top_scorer_update")
    preview = build_candidate(candidate_id=12, content_type="preview")

    assert tuesday_scheduler.is_candidate_publishable(ranking) is True
    assert thursday_scheduler.is_candidate_publishable(top_scorer) is True
    assert saturday_scheduler.is_candidate_publishable(preview) is True


def test_scheduler_respects_weekday_morning_and_evening_slots() -> None:
    scheduler = XPublicationScheduler(settings=build_settings(timezone="Europe/Madrid"))
    ranking = build_candidate(candidate_id=20, content_type="ranking")

    assert scheduler.is_candidate_publishable(ranking, now=datetime(2026, 3, 17, 9, 29)) is False
    assert scheduler.is_candidate_publishable(ranking, now=datetime(2026, 3, 17, 9, 30)) is True
    assert scheduler.is_candidate_publishable(ranking, now=datetime(2026, 3, 17, 19, 30)) is True


def test_scheduler_uses_active_slot_types(tmp_path: Path) -> None:
    schedule_path = tmp_path / "publication_schedule.json"
    schedule_path.write_text(
        json.dumps(
            {
                "martes": {
                    "slots": [
                        {"publish_after": "09:30", "publish_limit": 1, "types": ["ranking"]},
                        {"publish_after": "19:30", "publish_limit": 2, "types": ["standings_roundup"]},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    scheduler = XPublicationScheduler(
        settings=build_settings(timezone="Europe/Madrid"),
        schedule_path=schedule_path,
    )
    ranking = build_candidate(candidate_id=21, content_type="ranking")
    standings = build_candidate(candidate_id=22, content_type="standings_roundup")
    day_schedule = scheduler.schedule.day("martes")

    assert day_schedule is not None
    assert [slot.publish_limit for slot in day_schedule.slots] == [1, 2]

    assert scheduler.is_candidate_publishable(ranking, now=datetime(2026, 3, 17, 9, 30)) is True
    assert scheduler.is_candidate_publishable(standings, now=datetime(2026, 3, 17, 9, 30)) is False
    assert scheduler.is_candidate_publishable(ranking, now=datetime(2026, 3, 17, 19, 30)) is False
    assert scheduler.is_candidate_publishable(standings, now=datetime(2026, 3, 17, 19, 30)) is True


def test_scheduler_keeps_legacy_single_slot_schedule(tmp_path: Path) -> None:
    schedule_path = tmp_path / "publication_schedule.json"
    schedule_path.write_text(
        json.dumps({"sabado": {"publish_after": "11:00", "types": ["preview"]}}),
        encoding="utf-8",
    )
    scheduler = XPublicationScheduler(
        settings=build_settings(timezone="Europe/Madrid"),
        schedule_path=schedule_path,
    )
    preview = build_candidate(candidate_id=23, content_type="preview")

    assert scheduler.is_candidate_publishable(preview, now=datetime(2026, 3, 21, 10, 59)) is False
    assert scheduler.is_candidate_publishable(preview, now=datetime(2026, 3, 21, 11, 0)) is True


def test_scheduler_respects_phase_service_when_configured() -> None:
    class _FakePhaseService:
        def is_candidate_allowed(self, candidate, *, reference_date=None):  # type: ignore[no-untyped-def]
            return candidate.competition_slug.endswith("_playoff")

    scheduler = XPublicationScheduler(
        settings=build_settings(timezone="Europe/Madrid"),
        now_provider=lambda: datetime(2026, 3, 16, 10, 0),
        phase_service=_FakePhaseService(),  # type: ignore[arg-type]
    )
    regular = build_candidate(candidate_id=30, content_type="results_roundup")
    playoff = build_candidate(candidate_id=31, content_type="results_roundup")
    playoff.competition_slug = "tercera_rfef_g11_playoff"

    assert scheduler.is_candidate_publishable(regular) is False
    assert scheduler.is_candidate_publishable(playoff) is True
