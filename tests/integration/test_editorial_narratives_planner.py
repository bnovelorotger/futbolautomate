from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.core.config import Settings
from app.core.enums import EditorialPlanningContent
from app.db.models import ContentCandidate
from app.schemas.editorial_planner import EditorialScheduleRule, EditorialWeeklySchedule
from app.services.editorial_planner import EditorialPlannerService
from tests.unit.services.test_editorial_narratives import build_session, seed_narratives_data


def build_settings() -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        timezone="Europe/Madrid",
    )


def test_editorial_planner_generates_metric_narratives_without_cross_competition_mix() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        schedule = EditorialWeeklySchedule(
            timezone="Europe/Madrid",
            weekly_plan={
                "domingo": [
                    EditorialScheduleRule(
                        competition_slug="tercera_rfef_g11",
                        content_type=EditorialPlanningContent.LATEST_RESULTS,
                        priority=100,
                    ),
                    EditorialScheduleRule(
                        competition_slug="segunda_rfef_g3_baleares",
                        content_type=EditorialPlanningContent.METRIC_NARRATIVE,
                        priority=68,
                    ),
                ]
            },
        )

        result = EditorialPlannerService(
            session,
            schedule=schedule,
            settings=build_settings(),
        ).generate_for_date(date(2026, 3, 15))
        session.commit()

        rows = session.execute(
            select(ContentCandidate).order_by(ContentCandidate.competition_slug.asc(), ContentCandidate.id.asc())
        ).scalars().all()
        tercera_rows = [row for row in rows if row.competition_slug == "tercera_rfef_g11"]
        segunda_rows = [row for row in rows if row.competition_slug == "segunda_rfef_g3_baleares"]

        assert result.total_tasks == 2
        assert tercera_rows
        assert segunda_rows
        assert all(row.content_type == "match_result" for row in tercera_rows)
        assert all(row.content_type == "metric_narrative" for row in segunda_rows)
        assert all("Torrent CF" not in row.text_draft and "UE Porreres" not in row.text_draft for row in tercera_rows)
        assert all("CD Llosetense" not in row.text_draft and "SD Portmany" not in row.text_draft for row in segunda_rows)
    finally:
        session.close()
