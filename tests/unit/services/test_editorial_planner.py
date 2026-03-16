from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import ContentType, EditorialPlanningContent
from app.db.base import Base
from app.db.models import Competition, ContentCandidate
from app.schemas.editorial_planner import EditorialScheduleRule, EditorialWeeklySchedule
from app.schemas.editorial_summary import (
    CompetitionEditorialSummary,
    EditorialAggregateMetrics,
    EditorialCalendarWindows,
    EditorialCompetitionState,
    EditorialRankings,
    EditorialSummaryMetadata,
)
from app.schemas.reporting import CompetitionMatchView, StandingView, TeamRankingView
from app.services.editorial_planner import EditorialPlannerService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def build_settings(**overrides) -> Settings:
    payload = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "timezone": "Europe/Madrid",
    }
    payload.update(overrides)
    return Settings(**payload)


def seed_competitions(session: Session) -> None:
    session.add_all(
        [
            Competition(
                code="tercera_rfef_g11",
                name="3a RFEF Grupo 11",
                normalized_name="3a rfef grupo 11",
                category_level=5,
                gender="male",
                region="Baleares",
                country="Spain",
                federation="RFEF",
                source_name="futbolme",
                source_competition_id="3047",
            ),
            Competition(
                code="segunda_rfef_g3_baleares",
                name="2a RFEF Grupo 3",
                normalized_name="2a rfef grupo 3",
                category_level=4,
                gender="male",
                region="Baleares",
                country="Spain",
                federation="RFEF",
                source_name="futbolme",
                source_competition_id="3059",
            ),
        ]
    )
    session.commit()


def build_schedule() -> EditorialWeeklySchedule:
    return EditorialWeeklySchedule(
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
                    content_type=EditorialPlanningContent.STANDINGS,
                    priority=80,
                ),
            ],
            "viernes": [
                EditorialScheduleRule(
                    competition_slug="tercera_rfef_g11",
                    content_type=EditorialPlanningContent.PREVIEW,
                    priority=90,
                )
            ],
        },
    )


def build_summary(competition_slug: str, competition_name: str) -> CompetitionEditorialSummary:
    if competition_slug == "tercera_rfef_g11":
        latest_results = [
            CompetitionMatchView(
                round_name="Jornada 25",
                match_date=date(2026, 3, 8),
                match_date_raw="domingo, 08 de marzo de 2026",
                match_time=time(12, 0),
                match_time_raw="12:00",
                kickoff_datetime=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                home_team="CD Llosetense",
                away_team="SD Portmany",
                home_score=3,
                away_score=0,
                status="finished",
                source_url="https://example.com/tercera/result-1",
            ),
            CompetitionMatchView(
                round_name="Jornada 25",
                match_date=date(2026, 3, 8),
                match_date_raw="domingo, 08 de marzo de 2026",
                match_time=time(17, 0),
                match_time_raw="17:00",
                kickoff_datetime=datetime(2026, 3, 8, 17, 0, tzinfo=timezone.utc),
                home_team="CD Manacor",
                away_team="CE Mercadal",
                home_score=2,
                away_score=1,
                status="finished",
                source_url="https://example.com/tercera/result-2",
            ),
        ]
        featured_home = "RCD Mallorca B"
        featured_away = "CE Santanyi"
    else:
        latest_results = [
            CompetitionMatchView(
                round_name="Jornada 26",
                match_date=date(2026, 3, 8),
                match_date_raw="domingo, 08 de marzo de 2026",
                match_time=time(18, 0),
                match_time_raw="18:00",
                kickoff_datetime=datetime(2026, 3, 8, 18, 0, tzinfo=timezone.utc),
                home_team="Torrent CF",
                away_team="UE Porreres",
                home_score=1,
                away_score=0,
                status="finished",
                source_url="https://example.com/segunda/result-1",
            ),
            CompetitionMatchView(
                round_name="Jornada 26",
                match_date=date(2026, 3, 8),
                match_date_raw="domingo, 08 de marzo de 2026",
                match_time=time(19, 0),
                match_time_raw="19:00",
                kickoff_datetime=datetime(2026, 3, 8, 19, 0, tzinfo=timezone.utc),
                home_team="UE Sant Andreu",
                away_team="CD Atletico Baleares",
                home_score=2,
                away_score=2,
                status="finished",
                source_url="https://example.com/segunda/result-2",
            ),
        ]
        featured_home = "UE Porreres"
        featured_away = "UE Sant Andreu"

    return CompetitionEditorialSummary(
        metadata=EditorialSummaryMetadata(
            competition_slug=competition_slug,
            competition_name=competition_name,
            reference_date=date(2026, 3, 15),
            generated_at=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
        ),
        competition_state=EditorialCompetitionState(
            total_teams=18,
            total_matches=306,
            played_matches=223,
            pending_matches=83,
        ),
        latest_results=latest_results,
        upcoming_matches=[
            CompetitionMatchView(
                round_name="Jornada 26",
                match_date=date(2026, 3, 20),
                match_date_raw="viernes, 20 de marzo de 2026",
                match_time=time(20, 0),
                match_time_raw="20:00",
                kickoff_datetime=datetime(2026, 3, 20, 20, 0, tzinfo=timezone.utc),
                home_team=featured_home,
                away_team=featured_away,
                status="scheduled",
                source_url=f"https://example.com/{competition_slug}/upcoming-1",
            )
        ],
        current_standings=[
            StandingView(position=1, team="RCD Mallorca B", points=63, played=25, goals_for=73, goals_against=16, goal_difference=57),
            StandingView(position=2, team="CD Manacor", points=61, played=25, goals_for=55, goals_against=27, goal_difference=28),
            StandingView(position=3, team="SCR Pena Deportiva", points=56, played=25, goals_for=50, goals_against=19, goal_difference=31),
        ],
        rankings=EditorialRankings(
            best_attack=TeamRankingView(team="RCD Mallorca B", value=73, position=1),
            best_defense=TeamRankingView(team="RCD Mallorca B", value=16, position=1),
            most_wins=TeamRankingView(team="RCD Mallorca B", value=20, position=1),
        ),
        calendar_windows=EditorialCalendarWindows(today=[], tomorrow=[], next_weekend=[]),
        editorial_news=[],
        aggregate_metrics=EditorialAggregateMetrics(
            total_goals_scored=637,
            average_goals_per_played_match=2.95,
            relevant_news_count=2,
        ),
    )


def test_editorial_planner_resolves_campaign_plan_for_date() -> None:
    session = build_session()
    try:
        service = EditorialPlannerService(
            session,
            schedule=build_schedule(),
            settings=build_settings(),
        )

        plan = service.plan_for_date(date(2026, 3, 15))

        assert plan.weekday_key == "sunday"
        assert plan.weekday_label == "domingo"
        assert plan.total_tasks == 2
        assert plan.tasks[0].competition_slug == "tercera_rfef_g11"
        assert plan.tasks[0].planning_type == EditorialPlanningContent.LATEST_RESULTS
        assert plan.tasks[0].target_content_type == ContentType.MATCH_RESULT
        assert plan.tasks[1].planning_type == EditorialPlanningContent.STANDINGS
        assert plan.tasks[1].target_content_type == ContentType.STANDINGS
    finally:
        session.close()


def test_editorial_planner_week_plan_spans_monday_to_sunday() -> None:
    session = build_session()
    try:
        service = EditorialPlannerService(
            session,
            schedule=build_schedule(),
            settings=build_settings(),
        )

        week_plan = service.week_plan(date(2026, 3, 15))

        assert week_plan.week_start == date(2026, 3, 9)
        assert week_plan.week_end == date(2026, 3, 15)
        assert len(week_plan.days) == 7
        assert week_plan.days[4].weekday_key == "friday"
        assert week_plan.days[4].total_tasks == 1
        assert week_plan.days[6].weekday_key == "sunday"
        assert week_plan.days[6].total_tasks == 2
    finally:
        session.close()


def test_editorial_planner_generates_only_planned_candidates() -> None:
    session = build_session()
    try:
        seed_competitions(session)
        service = EditorialPlannerService(
            session,
            schedule=build_schedule(),
            settings=build_settings(),
        )

        def fake_summary_builder(competition_code: str, **kwargs) -> CompetitionEditorialSummary:
            names = {
                "tercera_rfef_g11": "3a RFEF Grupo 11",
                "segunda_rfef_g3_baleares": "2a RFEF Grupo 3",
            }
            return build_summary(competition_code, names[competition_code])

        service.generator.summary_service.build_competition_summary = fake_summary_builder

        result = service.generate_for_date(date(2026, 3, 15))
        session.commit()

        rows = session.execute(select(ContentCandidate).order_by(ContentCandidate.id.asc())).scalars().all()

        assert result.total_tasks == 2
        assert result.total_generated == 3
        assert result.total_inserted == 3
        assert len(rows) == 3
        assert sorted(row.content_type for row in rows) == [
            "match_result",
            "match_result",
            "standings",
        ]
        assert {row.competition_slug for row in rows} == {
            "tercera_rfef_g11",
            "segunda_rfef_g3_baleares",
        }
        assert all(row.status == "draft" for row in rows)
        tercera_rows = [row for row in rows if row.competition_slug == "tercera_rfef_g11"]
        segunda_rows = [row for row in rows if row.competition_slug == "segunda_rfef_g3_baleares"]
        assert all("Torrent CF" not in row.text_draft and "UE Porreres" not in row.text_draft for row in tercera_rows)
        assert all("CD Llosetense" not in row.text_draft and "CE Mercadal" not in row.text_draft for row in segunda_rows)
        counts_by_planning_type = {
            row.task.planning_type: row.generated_count
            for row in result.rows
        }
        assert counts_by_planning_type[EditorialPlanningContent.LATEST_RESULTS] == 2
        assert counts_by_planning_type[EditorialPlanningContent.STANDINGS] == 1
    finally:
        session.close()


def test_editorial_planner_rejects_mismatched_summary_competition() -> None:
    session = build_session()
    try:
        seed_competitions(session)
        mismatch_schedule = EditorialWeeklySchedule(
            timezone="Europe/Madrid",
            weekly_plan={
                "domingo": [
                    EditorialScheduleRule(
                        competition_slug="tercera_rfef_g11",
                        content_type=EditorialPlanningContent.LATEST_RESULTS,
                        priority=100,
                    )
                ]
            },
        )
        service = EditorialPlannerService(
            session,
            schedule=mismatch_schedule,
            settings=build_settings(),
        )

        def wrong_summary_builder(competition_code: str, **kwargs) -> CompetitionEditorialSummary:
            return build_summary("segunda_rfef_g3_baleares", "2a RFEF Grupo 3")

        service.generator.summary_service.build_competition_summary = wrong_summary_builder

        with pytest.raises(ValueError, match="no corresponde a la competicion pedida"):
            service.generate_for_date(date(2026, 3, 15))

        rows = session.execute(select(ContentCandidate)).scalars().all()
        assert rows == []
    finally:
        session.close()
