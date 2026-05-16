from __future__ import annotations

from datetime import date, datetime, timezone

from app.db.models import Competition, Standing, Team
from app.services.team_analytics import TeamAnalyticsService
from tests.unit.db.repositories.test_standings_repository import seed_team_analytics_competition
from tests.unit.services.test_editorial_narratives import build_session


def test_team_analytics_computes_recent_form_splits_and_season_pace() -> None:
    session = build_session()
    try:
        seed_team_analytics_competition(session)
        service = TeamAnalyticsService(session)

        result = service.preview_for_competition(
            "team_analytics_g11",
            reference_date=date(2026, 3, 10),
        )

        alpha = next(row for row in result.rows if row.team == "CE Alpha")

        assert alpha.position == 1
        assert alpha.overall_points_per_game == 2.3
        assert alpha.last_ten.matches_considered == 10
        assert alpha.last_ten.sequence == "WWWWDWWLDW"
        assert alpha.last_ten.points == 23
        assert alpha.last_five.matches_considered == 5
        assert alpha.last_five.sequence == "WWWWD"
        assert alpha.last_five.points == 13
        assert alpha.recent_trend.direction == "improving"
        assert alpha.recent_trend.delta_points_per_game == 0.3
        assert alpha.home_split.points == 12
        assert alpha.home_split.points_per_game == 2.4
        assert alpha.home_split.win_rate_percentage == 80.0
        assert alpha.away_split.points == 11
        assert alpha.away_split.points_per_game == 2.2
        assert alpha.season_pace.matches_scheduled == 12
        assert alpha.season_pace.matches_remaining == 2
        assert alpha.season_pace.projected_additional_points == 4.6
        assert alpha.season_pace.projected_final_points == 27.6
        assert alpha.defensive_solidity.total_goals == 2
        assert alpha.defensive_solidity.goals_per_match == 0.4
        assert alpha.attacking_efficiency.total_goals == 10
        assert alpha.attacking_efficiency.goals_per_match == 2.0
        assert alpha.goal_difference_trend.direction == "improving"
        assert alpha.goal_difference_trend.opening_goal_difference_per_match == 1.0
        assert alpha.goal_difference_trend.recent_goal_difference_per_match == 1.6
        assert alpha.goal_difference_trend.delta_goal_difference_per_match == 0.6
    finally:
        session.close()


def test_team_analytics_handles_competitions_without_match_history() -> None:
    session = build_session()
    try:
        competition = Competition(
            code="team_analytics_empty",
            name="Team Analytics Empty",
            normalized_name="team-analytics-empty",
            category_level=4,
            gender="male",
            region="Baleares",
            country="Spain",
            federation="RFEF",
            source_name="futbolme",
            source_competition_id="team_analytics_empty",
        )
        session.add(competition)
        session.flush()

        team = Team(
            name="CE Lone",
            normalized_name="team-analytics-empty-ce-lone",
            gender="male",
        )
        session.add(team)
        session.flush()

        session.add(
            Standing(
                source_name="futbolme",
                source_url="https://example.com/team-analytics-empty/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo test",
                position=1,
                team_id=team.id,
                team_raw="CE Lone",
                played=0,
                wins=0,
                draws=0,
                losses=0,
                goals_for=0,
                goals_against=0,
                goal_difference=0,
                points=0,
                form_text=None,
                scraped_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
                content_hash="team-analytics-empty-standing",
                extra_data=None,
            )
        )
        session.commit()

        service = TeamAnalyticsService(session)
        result = service.preview_for_competition(
            "team_analytics_empty",
            reference_date=date(2026, 3, 10),
        )

        row = result.rows[0]
        assert row.team == "CE Lone"
        assert row.last_five.matches_considered == 0
        assert row.home_split.played == 0
        assert row.away_split.played == 0
        assert row.season_pace.matches_remaining == 0
        assert row.defensive_solidity.goals_per_match == 0.0
        assert row.goal_difference_trend.direction == "stable"
    finally:
        session.close()
