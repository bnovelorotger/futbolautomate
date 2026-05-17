from __future__ import annotations

from datetime import UTC, date, datetime

from app.db.models import ContentCandidate
from app.schemas.editorial_day_plan import EditorialDayPlanReport
from app.services.editorial_day_plan_service import EditorialDayPlanService
from tests.unit.services.service_test_support import build_session, build_settings


def _candidate(
    *,
    candidate_id: int,
    content_type: str,
    status: str,
    reference_date: str,
    competition_name: str,
    priority: int = 0,
) -> ContentCandidate:
    timestamp = datetime(2026, 5, 18, 7, 0, tzinfo=UTC)
    return ContentCandidate(
        id=candidate_id,
        competition_slug=f"slug-{candidate_id}",
        content_type=content_type,
        priority=priority,
        status=status,
        text_draft=f"draft {candidate_id}",
        payload_json={
            "reference_date": reference_date,
            "competition_name": competition_name,
        },
        source_summary_hash=f"hash-{candidate_id}",
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_editorial_day_plan_groups_today_candidates_and_statuses() -> None:
    session = build_session()
    session.add_all(
        [
            _candidate(
                candidate_id=1,
                content_type="results_roundup",
                status="published",
                reference_date="2026-05-18",
                competition_name="DH Mallorca",
                priority=10,
            ),
            _candidate(
                candidate_id=2,
                content_type="preview",
                status="approved",
                reference_date="2026-05-18",
                competition_name="Tercera RFEF",
                priority=5,
            ),
            _candidate(
                candidate_id=3,
                content_type="preview",
                status="draft",
                reference_date="2026-05-18",
                competition_name="Regional Preferente",
                priority=2,
            ),
            _candidate(
                candidate_id=4,
                content_type="viral_story",
                status="rejected",
                reference_date="2026-05-18",
                competition_name="Liga Nacional",
                priority=1,
            ),
            _candidate(
                candidate_id=5,
                content_type="standings_roundup",
                status="published",
                reference_date="2026-05-17",
                competition_name="Debe quedar fuera",
                priority=1,
            ),
        ]
    )
    session.commit()

    service = EditorialDayPlanService(session, settings=build_settings())
    report = service.build_report(target_date=date(2026, 5, 18))

    assert isinstance(report, EditorialDayPlanReport)
    assert report.status.total_candidates == 4
    assert report.status.published_count == 1
    assert report.status.approved_count == 1
    assert report.status.draft_count == 1
    assert report.status.rejected_count == 1
    assert report.status.pending_count == 2
    assert [item.content_type for item in report.by_content_type] == ["preview", "results_roundup", "viral_story"]
    assert [entry.status for entry in report.entries] == ["approved", "draft", "published", "rejected"]


def test_editorial_day_plan_render_telegram_includes_schedule_and_entries() -> None:
    session = build_session()
    session.add(
        _candidate(
            candidate_id=10,
            content_type="results_roundup",
            status="published",
            reference_date="2026-05-19",
            competition_name="DH Mallorca",
            priority=10,
        )
    )
    session.commit()

    service = EditorialDayPlanService(session, settings=build_settings())
    report = service.build_report(target_date=date(2026, 5, 19))
    message = service.render_telegram(report)

    assert "agenda editorial 2026-05-19" in message
    assert "dia: martes" in message
    assert "ya publicadas: 1" in message
    assert "results_roundup" in message
    assert "DH Mallorca" in message

