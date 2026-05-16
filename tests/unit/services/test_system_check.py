from __future__ import annotations

from datetime import date, time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.services.competition_catalog_service import CompetitionCatalogService
from app.services.system_check import SystemCheckService
from tests.unit.services.test_editorial_narratives import seed_competition, seed_narratives_data


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def build_settings() -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        timezone="Europe/Madrid",
    )


def test_system_check_reports_missing_and_ready_competitions() -> None:
    session = build_session()
    try:
        CompetitionCatalogService(session).seed_competitions(integrated_only=True, missing_only=True)
        seed_narratives_data(session)

        report = SystemCheckService(session, settings=build_settings()).editorial_readiness()

        assert report.integrated_catalog_count == 7
        assert report.seeded_integrated_count == 7
        assert report.export_base_ready is True
        assert report.export_base_path.endswith("exports\\export_base.json") or report.export_base_path.endswith("exports/export_base.json")
        rows = {row.code: row for row in report.rows}
        assert rows["tercera_rfef_g11"].planner_ready is True
        assert rows["segunda_rfef_g3_baleares"].planner_ready is True
        assert rows["division_honor_mallorca"].planner_ready is False
        assert rows["primera_rfef_baleares"].planner_ready is False
        assert rows["tercera_federacion_femenina_g11"].planner_ready is False
        assert rows["division_honor_ibiza_form"].planner_ready is False
        assert rows["division_honor_menorca"].planner_ready is False
        assert "finished_matches" in rows["division_honor_mallorca"].missing_dependencies
        assert "standings" in rows["division_honor_mallorca"].missing_dependencies
        assert "scheduled_matches" in rows["primera_rfef_baleares"].missing_dependencies
        assert rows["tercera_rfef_g11"].scorer_season == "2025-26 (0/4 covered, backlog=4)"
    finally:
        session.close()


def test_system_check_reports_missing_match_events_for_top_scorer_readiness() -> None:
    session = build_session()
    try:
        CompetitionCatalogService(session).seed_competitions(integrated_only=True, missing_only=True)
        seed_competition(
            session,
            code="division_honor_mallorca",
            name="Division Honor Mallorca",
            teams=["Portol FC", "Inter Manacor", "CD Serverense", "CE Esporles"],
            standings_rows=[
                {"position": 1, "team": "Portol FC", "played": 2, "wins": 2, "draws": 0, "losses": 0, "goals_for": 4, "goals_against": 1, "goal_difference": 3, "points": 6},
                {"position": 2, "team": "Inter Manacor", "played": 2, "wins": 1, "draws": 1, "losses": 0, "goals_for": 3, "goals_against": 1, "goal_difference": 2, "points": 4},
            ],
            match_rows=[
                {"round_name": "Jornada 2", "match_date": date(2026, 3, 14), "match_time": time(18, 0), "home_team": "Portol FC", "away_team": "CD Serverense", "home_score": 2, "away_score": 1},
                {"round_name": "Jornada 1", "match_date": date(2026, 3, 7), "match_time": time(17, 0), "home_team": "Inter Manacor", "away_team": "CE Esporles", "home_score": 1, "away_score": 0},
            ],
        )

        report = SystemCheckService(session, settings=build_settings()).editorial_readiness()
        row = {item.code: item for item in report.rows}["division_honor_mallorca"]

        assert row.finished_matches_count == 2
        assert row.scorer_matches_count == 0
        assert row.goal_events_count == 0
        assert row.scorer_season == "2025-26 (0/2 covered, backlog=2)"
        assert "match_events" in row.missing_dependencies
    finally:
        session.close()
