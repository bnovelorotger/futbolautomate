from __future__ import annotations

from datetime import date, time

from sqlalchemy import select

from app.core.enums import EditorialPlanningContent
from app.db.models import ContentCandidate
from app.services.competition_catalog_service import CompetitionCatalogService
from app.services.editorial_ops import EditorialOperationsService
from tests.unit.services.test_match_importance import add_scheduled_match
from tests.unit.services.test_editorial_narratives import build_session, seed_competition, seed_narratives_data


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

        assert preview.total_tasks == 24
        assert preview.ready_tasks == 5
        assert preview.blocked_tasks == 19
        assert preview.expected_total == 5
        assert run.generated_total == 5
        assert run.inserted_total == 5
        assert run.blocked_tasks == 19
        assert len(rows) == 5
        assert {row.content_type for row in rows} == {"results_roundup", "standings_roundup", "race_narrative"}
        race_row = next(row for row in rows if row.content_type == "race_narrative")
        assert "team_analytics" in race_row.payload_json["source_payload"]
        assert "puntos por partido en sus ultimos 5" in race_row.text_draft
    finally:
        session.close()


def test_editorial_ops_run_daily_generates_narrative_duo_for_available_wednesday_data() -> None:
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
        generated_competitions = {
            "tercera_rfef_g11",
            "segunda_rfef_g3_baleares",
        }

        assert run.total_tasks == 6
        assert metric_rows
        assert viral_rows
        assert {row.competition_slug for row in metric_rows} == generated_competitions
        assert {row.competition_slug for row in viral_rows} == generated_competitions
    finally:
        session.close()


def test_editorial_ops_preview_and_run_daily_generate_featured_match_drafts_on_friday() -> None:
    session = build_session()
    try:
        CompetitionCatalogService(session).seed_competitions(integrated_only=True, missing_only=True)
        seed_narratives_data(session)
        seed_competition(
            session,
            code="division_honor_mallorca",
            name="Division Honor Mallorca",
            teams=["Portol FC", "Inter Manacor", "CD Serverense", "CE Esporles"],
            standings_rows=[
                {"position": 1, "team": "Portol FC", "played": 12, "wins": 9, "draws": 2, "losses": 1, "goals_for": 21, "goals_against": 9, "goal_difference": 12, "points": 29},
                {"position": 2, "team": "Inter Manacor", "played": 12, "wins": 9, "draws": 1, "losses": 2, "goals_for": 20, "goals_against": 10, "goal_difference": 10, "points": 28},
                {"position": 3, "team": "CD Serverense", "played": 12, "wins": 7, "draws": 2, "losses": 3, "goals_for": 16, "goals_against": 12, "goal_difference": 4, "points": 23},
                {"position": 4, "team": "CE Esporles", "played": 12, "wins": 6, "draws": 2, "losses": 4, "goals_for": 14, "goals_against": 13, "goal_difference": 1, "points": 20},
            ],
            match_rows=[
                {"round_name": "Jornada 12", "match_date": date(2026, 3, 14), "match_time": time(18, 0), "home_team": "Portol FC", "away_team": "CD Serverense", "home_score": 2, "away_score": 1},
                {"round_name": "Jornada 11", "match_date": date(2026, 3, 7), "match_time": time(17, 0), "home_team": "Inter Manacor", "away_team": "CE Esporles", "home_score": 1, "away_score": 0},
            ],
        )
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="featured-top-clash",
            match_date=date(2026, 3, 20),
            match_time=time(20, 0),
            home_team="CD Llosetense",
            away_team="SD Portmany",
        )
        add_scheduled_match(
            session,
            competition_code="segunda_rfef_g3_baleares",
            external_id="featured-segunda-clash",
            match_date=date(2026, 3, 20),
            match_time=time(19, 30),
            home_team="UE Sant Andreu",
            away_team="CD Atletico Baleares",
        )
        add_scheduled_match(
            session,
            competition_code="division_honor_mallorca",
            external_id="featured-dh-clash",
            match_date=date(2026, 3, 20),
            match_time=time(18, 45),
            home_team="Portol FC",
            away_team="Inter Manacor",
        )
        service = EditorialOperationsService(session)

        preview = service.preview_day(date(2026, 3, 20))
        run = service.run_day(date(2026, 3, 20))
        session.commit()

        rows = session.execute(select(ContentCandidate).order_by(ContentCandidate.id.asc())).scalars().all()
        featured_rows = [row for row in rows if row.content_type in {"featured_match_preview", "featured_match_event"}]
        featured_preview_rows = [
            row
            for row in preview.rows
            if row.planning_type == EditorialPlanningContent.FEATURED_MATCH_PREVIEW
        ]
        match_impact_rows = [
            row
            for row in preview.rows
            if row.planning_type == EditorialPlanningContent.MATCH_IMPACT_SCENARIO
        ]

        assert preview.total_tasks == 10
        assert preview.ready_tasks == 5
        assert preview.blocked_tasks == 5
        assert len(featured_preview_rows) == 5
        assert len(match_impact_rows) == 5
        segunda_featured_row = next(
            row for row in featured_preview_rows if row.competition_slug == "segunda_rfef_g3_baleares"
        )
        tercera_featured_row = next(
            row for row in featured_preview_rows if row.competition_slug == "tercera_rfef_g11"
        )
        division_honor_featured_row = next(
            row for row in featured_preview_rows if row.competition_slug == "division_honor_mallorca"
        )
        assert segunda_featured_row.expected_count == 0
        assert segunda_featured_row.missing_dependencies == ["no_candidates_available"]
        assert tercera_featured_row.expected_count == 2
        assert not tercera_featured_row.missing_dependencies
        assert division_honor_featured_row.expected_count == 2
        assert not division_honor_featured_row.missing_dependencies
        segunda_match_impact_row = next(
            row for row in match_impact_rows if row.competition_slug == "segunda_rfef_g3_baleares"
        )
        tercera_match_impact_row = next(
            row for row in match_impact_rows if row.competition_slug == "tercera_rfef_g11"
        )
        division_honor_match_impact_row = next(
            row for row in match_impact_rows if row.competition_slug == "division_honor_mallorca"
        )
        assert segunda_match_impact_row.expected_count == 1
        assert not segunda_match_impact_row.missing_dependencies
        assert tercera_match_impact_row.expected_count == 1
        assert not tercera_match_impact_row.missing_dependencies
        assert division_honor_match_impact_row.expected_count == 1
        assert not division_honor_match_impact_row.missing_dependencies
        assert run.generated_total == 7
        assert featured_rows
        assert all(row.status == "draft" for row in featured_rows)
        assert {row.competition_slug for row in featured_rows} == {
            "tercera_rfef_g11",
            "division_honor_mallorca",
        }
        assert any(row.content_type == "match_impact_scenario" for row in rows)
    finally:
        session.close()


def test_editorial_ops_featured_match_marks_no_candidates_when_top_match_is_not_strong_enough() -> None:
    session = build_session()
    try:
        CompetitionCatalogService(session).seed_competitions(integrated_only=True, missing_only=True)
        seed_narratives_data(session)
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="low-interest-clash",
            match_date=date(2026, 3, 20),
            match_time=time(18, 0),
            home_team="CD Llosetense",
            away_team="CD Manacor",
        )
        service = EditorialOperationsService(session)
        service.match_importance.build_candidate_drafts = lambda *args, **kwargs: []

        preview = service.preview_day(date(2026, 3, 20))

        featured_row = next(
            row
            for row in preview.rows
            if row.competition_slug == "tercera_rfef_g11"
            and row.planning_type == EditorialPlanningContent.FEATURED_MATCH_PREVIEW
        )
        assert featured_row.expected_count == 0
        assert featured_row.missing_dependencies == ["no_candidates_available"]
    finally:
        session.close()
