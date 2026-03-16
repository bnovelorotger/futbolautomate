from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import NarrativeMetricType
from app.db.base import Base
from app.db.models import Competition, ContentCandidate, Match, Standing, Team
from app.services.editorial_narratives import EditorialNarrativesService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def seed_competition(
    session: Session,
    *,
    code: str,
    name: str,
    teams: list[str],
    standings_rows: list[dict],
    match_rows: list[dict],
) -> None:
    competition = session.scalar(select(Competition).where(Competition.code == code))
    if competition is None:
        competition = Competition(
            code=code,
            name=name,
            normalized_name=name.lower(),
            category_level=4,
            gender="male",
            region="Baleares",
            country="Spain",
            federation="RFEF",
            source_name="futbolme",
            source_competition_id=code,
        )
        session.add(competition)
        session.flush()

    team_map: dict[str, Team] = {}
    for team_name in teams:
        normalized_name = f"{code}-{team_name}".lower().replace(" ", "-")
        team = session.scalar(select(Team).where(Team.normalized_name == normalized_name))
        if team is None:
            team = Team(
                name=team_name,
                normalized_name=normalized_name,
                gender="male",
            )
            session.add(team)
            session.flush()
        team_map[team_name] = team

    scraped_at = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    for index, row in enumerate(standings_rows, start=1):
        session.add(
            Standing(
                source_name="futbolme",
                source_url=f"https://example.com/{code}/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo test",
                position=row["position"],
                team_id=team_map[row["team"]].id,
                team_raw=row["team"],
                played=row["played"],
                wins=row["wins"],
                draws=row["draws"],
                losses=row["losses"],
                goals_for=row["goals_for"],
                goals_against=row["goals_against"],
                goal_difference=row["goal_difference"],
                points=row["points"],
                form_text=None,
                scraped_at=scraped_at,
                content_hash=f"{code}-standing-{index}",
                extra_data=None,
            )
        )

    for index, row in enumerate(match_rows, start=1):
        session.add(
            Match(
                external_id=f"{code}-match-{index}",
                source_name="futbolme",
                source_url=f"https://example.com/{code}/match-{index}",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo test",
                round_name=row["round_name"],
                raw_match_date=row["match_date"].isoformat(),
                raw_match_time=row["match_time"].strftime("%H:%M"),
                match_date=row["match_date"],
                match_time=row["match_time"],
                kickoff_datetime=datetime.combine(row["match_date"], row["match_time"], tzinfo=timezone.utc),
                home_team_id=team_map[row["home_team"]].id,
                away_team_id=team_map[row["away_team"]].id,
                home_team_raw=row["home_team"],
                away_team_raw=row["away_team"],
                home_score=row["home_score"],
                away_score=row["away_score"],
                status="finished",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash=f"{code}-match-hash-{index}",
                extra_data=None,
            )
        )

    session.commit()


def seed_narratives_data(session: Session) -> None:
    seed_competition(
        session,
        code="tercera_rfef_g11",
        name="3a RFEF Grupo 11",
        teams=["CD Llosetense", "SD Portmany", "CE Mercadal", "CD Manacor"],
        standings_rows=[
            {"position": 1, "team": "CD Llosetense", "played": 12, "wins": 10, "draws": 1, "losses": 1, "goals_for": 24, "goals_against": 10, "goal_difference": 14, "points": 31},
            {"position": 2, "team": "SD Portmany", "played": 12, "wins": 8, "draws": 3, "losses": 1, "goals_for": 18, "goals_against": 7, "goal_difference": 11, "points": 27},
            {"position": 3, "team": "CE Mercadal", "played": 12, "wins": 7, "draws": 2, "losses": 3, "goals_for": 17, "goals_against": 13, "goal_difference": 4, "points": 23},
            {"position": 4, "team": "CD Manacor", "played": 12, "wins": 6, "draws": 2, "losses": 4, "goals_for": 15, "goals_against": 15, "goal_difference": 0, "points": 20},
        ],
        match_rows=[
            {"round_name": "Jornada 12", "match_date": date(2026, 3, 14), "match_time": time(18, 0), "home_team": "CD Llosetense", "away_team": "SD Portmany", "home_score": 2, "away_score": 0},
            {"round_name": "Jornada 11", "match_date": date(2026, 3, 7), "match_time": time(17, 0), "home_team": "CE Mercadal", "away_team": "CD Llosetense", "home_score": 0, "away_score": 1},
            {"round_name": "Jornada 10", "match_date": date(2026, 2, 28), "match_time": time(16, 0), "home_team": "CD Llosetense", "away_team": "CD Manacor", "home_score": 3, "away_score": 1},
            {"round_name": "Jornada 9", "match_date": date(2026, 2, 21), "match_time": time(12, 0), "home_team": "SD Portmany", "away_team": "CD Llosetense", "home_score": 1, "away_score": 1},
        ],
    )
    seed_competition(
        session,
        code="segunda_rfef_g3_baleares",
        name="2a RFEF Grupo 3",
        teams=["Torrent CF", "UE Porreres", "UE Sant Andreu", "CD Atletico Baleares"],
        standings_rows=[
            {"position": 1, "team": "UE Sant Andreu", "played": 12, "wins": 8, "draws": 2, "losses": 2, "goals_for": 20, "goals_against": 9, "goal_difference": 11, "points": 26},
            {"position": 2, "team": "CD Atletico Baleares", "played": 12, "wins": 7, "draws": 3, "losses": 2, "goals_for": 18, "goals_against": 10, "goal_difference": 8, "points": 24},
            {"position": 3, "team": "Torrent CF", "played": 12, "wins": 6, "draws": 4, "losses": 2, "goals_for": 16, "goals_against": 11, "goal_difference": 5, "points": 22},
            {"position": 4, "team": "UE Porreres", "played": 12, "wins": 5, "draws": 3, "losses": 4, "goals_for": 14, "goals_against": 13, "goal_difference": 1, "points": 18},
        ],
        match_rows=[
            {"round_name": "Jornada 12", "match_date": date(2026, 3, 14), "match_time": time(18, 30), "home_team": "Torrent CF", "away_team": "UE Porreres", "home_score": 1, "away_score": 0},
            {"round_name": "Jornada 11", "match_date": date(2026, 3, 7), "match_time": time(19, 0), "home_team": "UE Sant Andreu", "away_team": "CD Atletico Baleares", "home_score": 2, "away_score": 2},
        ],
    )


def test_editorial_narratives_builds_expected_metrics_and_streaks() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        service = EditorialNarrativesService(session)

        result = service.preview_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 15))

        types = {row.narrative_type for row in result.rows}
        assert types == {
            NarrativeMetricType.WIN_STREAK,
            NarrativeMetricType.UNBEATEN_STREAK,
            NarrativeMetricType.BEST_ATTACK,
            NarrativeMetricType.BEST_DEFENSE,
            NarrativeMetricType.MOST_WINS,
            NarrativeMetricType.GOALS_AVERAGE,
        }
        win_row = next(row for row in result.rows if row.narrative_type == NarrativeMetricType.WIN_STREAK)
        unbeaten_row = next(row for row in result.rows if row.narrative_type == NarrativeMetricType.UNBEATEN_STREAK)
        goals_row = next(row for row in result.rows if row.narrative_type == NarrativeMetricType.GOALS_AVERAGE)

        assert win_row.team == "CD Llosetense"
        assert win_row.metric_value == 3
        assert unbeaten_row.metric_value == 4
        assert goals_row.metric_value == 2.25
        assert "2.25 goles por partido" in goals_row.text_draft
    finally:
        session.close()


def test_editorial_narratives_generate_persists_metric_candidates_without_cross_competition_mix() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        service = EditorialNarrativesService(session)

        result = service.generate_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 15))
        session.commit()

        rows = session.execute(select(ContentCandidate).order_by(ContentCandidate.id.asc())).scalars().all()

        assert result.stats.inserted == len(result.rows)
        assert len(rows) == len(result.rows)
        assert all(row.competition_slug == "tercera_rfef_g11" for row in rows)
        assert all(row.content_type == "metric_narrative" for row in rows)
        assert all("Torrent CF" not in row.text_draft and "UE Porreres" not in row.text_draft for row in rows)
    finally:
        session.close()
