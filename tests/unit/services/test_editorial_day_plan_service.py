from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.core.enums import ContentType, EditorialPlanningContent
from app.db.models import ContentCandidate
from app.schemas.editorial_day_plan import EditorialDayPlanReport
from app.schemas.editorial_ops import EditorialOpsPreviewResult, EditorialOpsTaskPreview
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


def test_editorial_day_plan_groups_today_preview_tasks_and_published_today() -> None:
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
                content_type="standings_roundup",
                status="approved",
                reference_date="2026-05-18",
                competition_name="Tercera RFEF",
                priority=5,
            ),
            _candidate(
                candidate_id=3,
                content_type="milestone_story",
                status="draft",
                reference_date="2026-05-18",
                competition_name="Regional Preferente",
                priority=2,
            ),
        ]
    )
    published = session.get(ContentCandidate, 1)
    assert published is not None
    published.external_publication_ref = "x-browser:2026-05-18T08:45:00+02:00"
    published.external_publication_timestamp = datetime(2026, 5, 18, 8, 45, tzinfo=UTC)
    session.commit()

    service = EditorialDayPlanService(session, settings=build_settings())
    service.editorial_ops.preview_day = lambda _target_date: EditorialOpsPreviewResult(
        date=date(2026, 5, 18),
        total_tasks=3,
        ready_tasks=2,
        blocked_tasks=1,
        expected_total=7,
        rows=[
            EditorialOpsTaskPreview(
                competition_slug="slug-1",
                competition_name="DH Mallorca",
                planning_type=EditorialPlanningContent.RESULTS_ROUNDUP,
                target_content_type=ContentType.RESULTS_ROUNDUP,
                priority=90,
                expected_count=3,
                missing_dependencies=[],
                excerpts=[],
            ),
            EditorialOpsTaskPreview(
                competition_slug="slug-2",
                competition_name="Tercera RFEF",
                planning_type=EditorialPlanningContent.STANDINGS_ROUNDUP,
                target_content_type=ContentType.STANDINGS_ROUNDUP,
                priority=80,
                expected_count=2,
                missing_dependencies=[],
                excerpts=[],
            ),
            EditorialOpsTaskPreview(
                competition_slug="slug-3",
                competition_name="Regional Preferente",
                planning_type=EditorialPlanningContent.MILESTONE_STORY,
                target_content_type=ContentType.MILESTONE_STORY,
                priority=70,
                expected_count=5,
                missing_dependencies=[],
                excerpts=[],
            ),
            EditorialOpsTaskPreview(
                competition_slug="slug-4",
                competition_name="Liga Nacional",
                planning_type=EditorialPlanningContent.TOP_SCORER_UPDATE,
                target_content_type=ContentType.TOP_SCORER_UPDATE,
                priority=60,
                expected_count=1,
                missing_dependencies=["match_events"],
                excerpts=[],
            ),
        ],
    )
    service.approval_policy.autoapprove = lambda **_kwargs: SimpleNamespace(
        rows=[
            SimpleNamespace(
                id=11,
                content_type=ContentType.RESULTS_ROUNDUP,
                autoapprovable=True,
                priority=90,
                competition_slug="slug-1",
            ),
            SimpleNamespace(
                id=12,
                content_type=ContentType.STANDINGS_ROUNDUP,
                autoapprovable=True,
                priority=80,
                competition_slug="slug-2",
            ),
            SimpleNamespace(
                id=14,
                content_type=ContentType.STANDINGS_ROUNDUP,
                autoapprovable=True,
                priority=79,
                competition_slug="slug-2",
            ),
            SimpleNamespace(
                id=13,
                content_type=ContentType.TOP_SCORER_UPDATE,
                autoapprovable=False,
                priority=60,
                competition_slug="slug-4",
            ),
        ]
    )
    session.add_all(
        [
            _candidate(
                candidate_id=11,
                content_type="results_roundup",
                status="draft",
                reference_date="2026-05-18",
                competition_name="DH Mallorca",
                priority=90,
            ),
            _candidate(
                candidate_id=12,
                content_type="standings_roundup",
                status="draft",
                reference_date="2026-05-18",
                competition_name="Tercera RFEF",
                priority=80,
            ),
            _candidate(
                candidate_id=14,
                content_type="standings_roundup",
                status="draft",
                reference_date="2026-05-18",
                competition_name="Tercera RFEF",
                priority=79,
            ),
        ]
    )
    session.commit()
    report = service.build_report(target_date=date(2026, 5, 18))

    assert isinstance(report, EditorialDayPlanReport)
    assert report.status.total_candidates == 11
    assert report.status.published_count == 1
    assert report.status.approved_count == 3
    assert report.status.draft_count == 1
    assert report.status.rejected_count == 1
    assert report.status.pending_count == 2
    assert report.schedule.publish_slots == ["09:30", "19:30"]
    assert [item.content_type for item in report.by_content_type] == [
        "results_roundup",
        "standings_roundup",
    ]
    assert [entry.status for entry in report.entries] == ["auto", "auto"]
    assert all(entry.content_type != "milestone_story" for entry in report.entries)


def test_editorial_day_plan_render_telegram_includes_schedule_and_entries() -> None:
    session = build_session()
    service = EditorialDayPlanService(session, settings=build_settings())
    service.editorial_ops.preview_day = lambda _target_date: EditorialOpsPreviewResult(
        date=date(2026, 5, 18),
        total_tasks=1,
        ready_tasks=1,
        blocked_tasks=0,
        expected_total=1,
        rows=[
            EditorialOpsTaskPreview(
                competition_slug="slug-10",
                competition_name="DH Mallorca",
                planning_type=EditorialPlanningContent.RESULTS_ROUNDUP,
                target_content_type=ContentType.RESULTS_ROUNDUP,
                priority=10,
                expected_count=1,
                missing_dependencies=[],
                excerpts=[],
            )
        ],
    )
    service.approval_policy.autoapprove = lambda **_kwargs: SimpleNamespace(
        rows=[
            SimpleNamespace(
                id=10,
                content_type=ContentType.RESULTS_ROUNDUP,
                autoapprovable=True,
                priority=10,
                competition_slug="slug-10",
            )
        ]
    )
    session.add(
        _candidate(
            candidate_id=10,
            content_type="results_roundup",
            status="draft",
            reference_date="2026-05-18",
            competition_name="DH Mallorca",
            priority=10,
        )
    )
    session.commit()
    report = service.build_report(target_date=date(2026, 5, 18))
    message = service.render_telegram(report)

    assert "agenda editorial 2026-05-18" in message
    assert "dia: lunes" in message
    assert "slots X: 09:30, 19:30" in message
    assert "publicadas de la jornada: 0" in message
    assert "publicables hoy: 1" in message
    assert "salida prevista en este slot: 1" in message
    assert "results_roundup" in message
    assert "DH Mallorca" in message
