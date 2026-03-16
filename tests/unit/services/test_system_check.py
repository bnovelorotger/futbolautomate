from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.services.competition_catalog_service import CompetitionCatalogService
from app.services.system_check import SystemCheckService
from tests.unit.services.test_editorial_narratives import seed_narratives_data


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def build_settings() -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        timezone="Europe/Madrid",
        typefully_api_key=None,
        typefully_api_url=None,
    )


def test_system_check_reports_missing_and_ready_competitions() -> None:
    session = build_session()
    try:
        CompetitionCatalogService(session).seed_competitions(integrated_only=True, missing_only=True)
        seed_narratives_data(session)

        report = SystemCheckService(session, settings=build_settings()).editorial_readiness()

        assert report.integrated_catalog_count == 3
        assert report.seeded_integrated_count == 3
        assert report.typefully_ready is False
        rows = {row.code: row for row in report.rows}
        assert rows["tercera_rfef_g11"].planner_ready is True
        assert rows["segunda_rfef_g3_baleares"].planner_ready is True
        assert rows["division_honor_mallorca"].planner_ready is False
        assert "finished_matches" in rows["division_honor_mallorca"].missing_dependencies
        assert "standings" in rows["division_honor_mallorca"].missing_dependencies
    finally:
        session.close()
