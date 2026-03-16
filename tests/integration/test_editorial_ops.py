from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.db.models import ContentCandidate
from app.services.competition_catalog_service import CompetitionCatalogService
from app.services.editorial_ops import EditorialOperationsService
from tests.unit.services.test_editorial_narratives import build_session, seed_narratives_data


def test_editorial_ops_preview_and_run_daily_for_real_schedule() -> None:
    session = build_session()
    try:
        CompetitionCatalogService(session).seed_competitions(integrated_only=True, missing_only=True)
        seed_narratives_data(session)
        service = EditorialOperationsService(session)

        preview = service.preview_day(date(2026, 3, 16))
        run = service.run_day(date(2026, 3, 16))
        session.commit()

        rows = session.execute(select(ContentCandidate).order_by(ContentCandidate.id.asc())).scalars().all()

        assert preview.total_tasks == 6
        assert preview.blocked_tasks == 2
        assert preview.expected_total == 8
        assert run.generated_total == 8
        assert run.inserted_total == 8
        assert run.blocked_tasks == 2
        assert len(rows) == 8
        assert {row.content_type for row in rows} == {"match_result", "standings"}
    finally:
        session.close()


def test_editorial_ops_run_daily_generates_metric_narratives_on_wednesday() -> None:
    session = build_session()
    try:
        CompetitionCatalogService(session).seed_competitions(integrated_only=True, missing_only=True)
        seed_narratives_data(session)
        service = EditorialOperationsService(session)

        run = service.run_day(date(2026, 3, 18))
        session.commit()

        rows = session.execute(select(ContentCandidate).order_by(ContentCandidate.id.asc())).scalars().all()
        metric_rows = [row for row in rows if row.content_type == "metric_narrative"]
        viral_rows = [row for row in rows if row.content_type == "viral_story"]

        assert run.total_tasks == 6
        assert metric_rows
        assert viral_rows
        assert {row.competition_slug for row in metric_rows} == {
            "tercera_rfef_g11",
            "segunda_rfef_g3_baleares",
        }
        assert {row.competition_slug for row in viral_rows} == {
            "tercera_rfef_g11",
            "segunda_rfef_g3_baleares",
        }
    finally:
        session.close()
