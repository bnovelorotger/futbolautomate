from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import select

from app.db.models import Competition, Match, Standing, Team
from app.db.repositories.standings import StandingRepository
from tests.unit.services.test_editorial_narratives import build_session


def seed_team_analytics_competition(session) -> Competition:
    competition = Competition(
        code="team_analytics_g11",
        name="Team Analytics G11",
        normalized_name="team-analytics-g11",
        category_level=4,
        gender="male",
        region="Baleares",
        country="Spain",
        federation="RFEF",
        source_name="futbolme",
        source_competition_id="team_analytics_g11",
    )
    session.add(competition)
    session.flush()

    teams = {}
    for team_name in ("CE Alpha", "CE Beta", "CE Gamma", "CE Delta"):
        team = Team(
            name=team_name,
            normalized_name=f"team-analytics-{team_name}".lower().replace(" ", "-"),
            gender="male",
        )
        session.add(team)
        session.flush()
        teams[team_name] = team

    standings_rows = [
        ("CE Alpha", 1, 10, 7, 2, 1, 18, 5, 13, 23),
        ("CE Beta", 2, 8, 4, 2, 2, 11, 10, 1, 14),
        ("CE Gamma", 3, 8, 3, 2, 3, 9, 9, 0, 11),
        ("CE Delta", 4, 8, 1, 2, 5, 7, 16, -9, 5),
    ]
    for index, row in enumerate(standings_rows, start=1):
        team_name, position, played, wins, draws, losses, goals_for, goals_against, goal_difference, points = row
        session.add(
            Standing(
                source_name="futbolme",
                source_url="https://example.com/team-analytics/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo test",
                position=position,
                team_id=teams[team_name].id,
                team_raw=team_name,
                played=played,
                wins=wins,
                draws=draws,
                losses=losses,
                goals_for=goals_for,
                goals_against=goals_against,
                goal_difference=goal_difference,
                points=points,
                form_text=None,
                scraped_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
                content_hash=f"standing-{index}",
                extra_data=None,
            )
        )

    matches = [
        (date(2026, 1, 4), "CE Alpha", "CE Beta", 1, 0, "finished"),
        (date(2026, 1, 11), "CE Gamma", "CE Alpha", 2, 2, "finished"),
        (date(2026, 1, 18), "CE Alpha", "CE Delta", 0, 1, "finished"),
        (date(2026, 1, 25), "CE Beta", "CE Alpha", 0, 3, "finished"),
        (date(2026, 2, 1), "CE Alpha", "CE Gamma", 2, 0, "finished"),
        (date(2026, 2, 8), "CE Delta", "CE Alpha", 1, 1, "finished"),
        (date(2026, 2, 15), "CE Alpha", "CE Beta", 4, 1, "finished"),
        (date(2026, 2, 22), "CE Gamma", "CE Alpha", 0, 1, "finished"),
        (date(2026, 3, 1), "CE Alpha", "CE Delta", 2, 0, "finished"),
        (date(2026, 3, 8), "CE Beta", "CE Alpha", 0, 2, "finished"),
        (date(2026, 3, 20), "CE Alpha", "CE Gamma", None, None, "scheduled"),
        (date(2026, 3, 27), "CE Delta", "CE Alpha", None, None, "scheduled"),
    ]
    for index, row in enumerate(matches, start=1):
        match_date, home_team, away_team, home_score, away_score, status = row
        session.add(
            Match(
                external_id=f"team-analytics-match-{index}",
                source_name="futbolme",
                source_url=f"https://example.com/team-analytics/match-{index}",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo test",
                round_name=f"Jornada {index}",
                raw_match_date=match_date.isoformat(),
                raw_match_time="18:00",
                match_date=match_date,
                match_time=time(18, 0),
                kickoff_datetime=datetime.combine(match_date, time(18, 0), tzinfo=timezone.utc),
                home_team_id=teams[home_team].id,
                away_team_id=teams[away_team].id,
                home_team_raw=home_team,
                away_team_raw=away_team,
                home_score=home_score,
                away_score=away_score,
                status=status,
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
                content_hash=f"match-{index}",
                extra_data=None,
            )
        )

    session.commit()
    return session.scalar(select(Competition).where(Competition.id == competition.id))


def test_team_venue_splits_build_home_and_away_aggregates() -> None:
    session = build_session()
    try:
        competition = seed_team_analytics_competition(session)
        repository = StandingRepository(session)

        rows = repository.team_venue_splits(competition.id, reference_date=date(2026, 3, 10))
        split_map = {(row.team, row.venue): row for row in rows}

        alpha_home = split_map[("CE Alpha", "home")]
        alpha_away = split_map[("CE Alpha", "away")]

        assert alpha_home.played == 5
        assert alpha_home.wins == 4
        assert alpha_home.losses == 1
        assert alpha_home.points == 12
        assert alpha_home.goals_for == 9
        assert alpha_home.goals_against == 2
        assert alpha_home.goal_difference == 7

        assert alpha_away.played == 5
        assert alpha_away.wins == 3
        assert alpha_away.draws == 2
        assert alpha_away.points == 11
        assert alpha_away.goals_for == 9
        assert alpha_away.goals_against == 3
    finally:
        session.close()


def test_team_schedule_counts_include_finished_and_scheduled_matches() -> None:
    session = build_session()
    try:
        competition = seed_team_analytics_competition(session)
        repository = StandingRepository(session)

        rows = repository.team_schedule_counts(competition.id)
        counts = {row.team: row.total_matches for row in rows}

        assert counts["CE Alpha"] == 12
        assert counts["CE Beta"] == 4
        assert counts["CE Gamma"] == 4
        assert counts["CE Delta"] == 4
    finally:
        session.close()
