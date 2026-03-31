from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import MatchWindow
from app.db.base import Base
from app.db.models import Competition, Match, Standing, Team
from app.services.competition_queries import CompetitionQueryService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def seed_competition_data(session: Session) -> None:
    competition = Competition(
        code="division_honor_mallorca",
        name="Division Honor Mallorca",
        normalized_name="division honor mallorca",
        category_level=6,
        gender="male",
        region="Mallorca",
        country="Spain",
        federation="FFIB",
        source_name="futbolme",
        source_competition_id="4018",
    )
    team_a = Team(name="CE Andratx B", normalized_name="ce andratx b", gender="male")
    team_b = Team(name="CE Sineu", normalized_name="ce sineu", gender="male")
    team_c = Team(name="CD Ferriolense", normalized_name="cd ferriolense", gender="male")
    session.add_all([competition, team_a, team_b, team_c])
    session.flush()

    scraped_at = datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            Standing(
                source_name="futbolme",
                source_url="https://example.com/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name=None,
                position=1,
                team_id=team_a.id,
                team_raw="CE Andratx B",
                played=24,
                wins=17,
                draws=3,
                losses=4,
                goals_for=50,
                goals_against=24,
                goal_difference=26,
                points=54,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="standing-a",
                extra_data=None,
            ),
            Standing(
                source_name="futbolme",
                source_url="https://example.com/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name=None,
                position=2,
                team_id=team_b.id,
                team_raw="CE Sineu",
                played=24,
                wins=14,
                draws=5,
                losses=5,
                goals_for=43,
                goals_against=19,
                goal_difference=24,
                points=47,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="standing-b",
                extra_data=None,
            ),
            Standing(
                source_name="futbolme",
                source_url="https://example.com/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name=None,
                position=3,
                team_id=team_c.id,
                team_raw="CD Ferriolense",
                played=24,
                wins=12,
                draws=6,
                losses=6,
                goals_for=49,
                goals_against=37,
                goal_difference=12,
                points=42,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="standing-c",
                extra_data=None,
            ),
        ]
    )

    session.add_all(
        [
            Match(
                external_id="m1",
                source_name="futbolme",
                source_url="https://example.com/m1",
                competition_id=competition.id,
                season="2025-26",
                group_name=None,
                round_name="Jornada 24",
                raw_match_date="sabado, 07 de marzo de 2026",
                raw_match_time="16:00",
                match_date=date(2026, 3, 7),
                match_time=time(16, 0),
                kickoff_datetime=datetime(2026, 3, 7, 16, 0, tzinfo=timezone.utc),
                home_team_id=team_a.id,
                away_team_id=team_b.id,
                home_team_raw="CE Andratx B",
                away_team_raw="CE Sineu",
                home_score=2,
                away_score=1,
                status="finished",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="match-1",
                extra_data=None,
            ),
            Match(
                external_id="m2",
                source_name="futbolme",
                source_url="https://example.com/m2",
                competition_id=competition.id,
                season="2025-26",
                group_name=None,
                round_name="Jornada 25",
                raw_match_date="sabado, 14 de marzo de 2026",
                raw_match_time="16:00",
                match_date=date(2026, 3, 14),
                match_time=time(16, 0),
                kickoff_datetime=datetime(2026, 3, 14, 16, 0, tzinfo=timezone.utc),
                home_team_id=team_a.id,
                away_team_id=team_c.id,
                home_team_raw="CE Andratx B",
                away_team_raw="CD Ferriolense",
                home_score=None,
                away_score=None,
                status="scheduled",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="match-2",
                extra_data=None,
            ),
            Match(
                external_id="m3",
                source_name="futbolme",
                source_url="https://example.com/m3",
                competition_id=competition.id,
                season="2025-26",
                group_name=None,
                round_name="Jornada 25",
                raw_match_date="domingo, 15 de marzo de 2026",
                raw_match_time="12:00",
                match_date=date(2026, 3, 15),
                match_time=time(12, 0),
                kickoff_datetime=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
                home_team_id=team_b.id,
                away_team_id=team_c.id,
                home_team_raw="CE Sineu",
                away_team_raw="CD Ferriolense",
                home_score=None,
                away_score=None,
                status="scheduled",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="match-3",
                extra_data=None,
            ),
            Match(
                external_id="m4",
                source_name="futbolme",
                source_url="https://example.com/m4",
                competition_id=competition.id,
                season="2025-26",
                group_name=None,
                round_name="Jornada 26",
                raw_match_date="sabado, 21 de marzo de 2026",
                raw_match_time="18:30",
                match_date=date(2026, 3, 21),
                match_time=time(18, 30),
                kickoff_datetime=datetime(2026, 3, 21, 18, 30, tzinfo=timezone.utc),
                home_team_id=team_c.id,
                away_team_id=team_a.id,
                home_team_raw="CD Ferriolense",
                away_team_raw="CE Andratx B",
                home_score=None,
                away_score=None,
                status="scheduled",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="match-4",
                extra_data=None,
            ),
        ]
    )
    session.commit()


def seed_group_with_tracked_teams(session: Session) -> None:
    competition = Competition(
        code="segunda_rfef_g3_baleares",
        name="2a RFEF Grupo 3",
        normalized_name="2a rfef grupo 3",
        category_level=4,
        gender="male",
        region="Spain",
        country="Spain",
        federation="RFEF",
        source_name="futbolme",
        source_competition_id="3059",
    )
    baleares = Team(name="CD Atlético Baleares", normalized_name="cd atletico baleares", gender="male")
    poblense = Team(name="UD Poblense", normalized_name="ud poblense", gender="male")
    porreres = Team(name="UE Porreres", normalized_name="ue porreres", gender="male")
    sant_andreu = Team(name="UE Sant Andreu", normalized_name="ue sant andreu", gender="male")
    reus = Team(name="Reus FC Reddis", normalized_name="reus fc reddis", gender="male")
    session.add_all([competition, baleares, poblense, porreres, sant_andreu, reus])
    session.flush()

    scraped_at = datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            Standing(
                source_name="futbolme",
                source_url="https://example.com/segunda/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                position=1,
                team_id=sant_andreu.id,
                team_raw="UE Sant Andreu",
                played=25,
                wins=15,
                draws=6,
                losses=4,
                goals_for=39,
                goals_against=20,
                goal_difference=19,
                points=51,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="segunda-standing-1",
                extra_data=None,
            ),
            Standing(
                source_name="futbolme",
                source_url="https://example.com/segunda/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                position=2,
                team_id=baleares.id,
                team_raw="CD Atlético Baleares",
                played=25,
                wins=14,
                draws=6,
                losses=5,
                goals_for=35,
                goals_against=18,
                goal_difference=17,
                points=48,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="segunda-standing-2",
                extra_data=None,
            ),
            Standing(
                source_name="futbolme",
                source_url="https://example.com/segunda/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                position=3,
                team_id=poblense.id,
                team_raw="UD Poblense",
                played=25,
                wins=13,
                draws=7,
                losses=5,
                goals_for=31,
                goals_against=19,
                goal_difference=12,
                points=46,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="segunda-standing-3",
                extra_data=None,
            ),
            Standing(
                source_name="futbolme",
                source_url="https://example.com/segunda/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                position=4,
                team_id=porreres.id,
                team_raw="UE Porreres",
                played=25,
                wins=12,
                draws=5,
                losses=8,
                goals_for=29,
                goals_against=24,
                goal_difference=5,
                points=41,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="segunda-standing-4",
                extra_data=None,
            ),
            Standing(
                source_name="futbolme",
                source_url="https://example.com/segunda/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                position=5,
                team_id=reus.id,
                team_raw="Reus FC Reddis",
                played=25,
                wins=10,
                draws=7,
                losses=8,
                goals_for=24,
                goals_against=23,
                goal_difference=1,
                points=37,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="segunda-standing-5",
                extra_data=None,
            ),
        ]
    )

    session.add_all(
        [
            Match(
                external_id="segunda-m1",
                source_name="futbolme",
                source_url="https://example.com/segunda/m1",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                round_name="Jornada 26",
                raw_match_date="domingo, 08 de marzo de 2026",
                raw_match_time="18:00",
                match_date=date(2026, 3, 8),
                match_time=time(18, 0),
                kickoff_datetime=datetime(2026, 3, 8, 18, 0, tzinfo=timezone.utc),
                home_team_id=sant_andreu.id,
                away_team_id=reus.id,
                home_team_raw="UE Sant Andreu",
                away_team_raw="Reus FC Reddis",
                home_score=1,
                away_score=0,
                status="finished",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="segunda-match-1",
                extra_data=None,
            ),
            Match(
                external_id="segunda-m2",
                source_name="futbolme",
                source_url="https://example.com/segunda/m2",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                round_name="Jornada 26",
                raw_match_date="sabado, 07 de marzo de 2026",
                raw_match_time="17:00",
                match_date=date(2026, 3, 7),
                match_time=time(17, 0),
                kickoff_datetime=datetime(2026, 3, 7, 17, 0, tzinfo=timezone.utc),
                home_team_id=poblense.id,
                away_team_id=sant_andreu.id,
                home_team_raw="UD Poblense",
                away_team_raw="UE Sant Andreu",
                home_score=2,
                away_score=1,
                status="finished",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="segunda-match-2",
                extra_data=None,
            ),
            Match(
                external_id="segunda-m3",
                source_name="futbolme",
                source_url="https://example.com/segunda/m3",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                round_name="Jornada 26",
                raw_match_date="viernes, 06 de marzo de 2026",
                raw_match_time="20:00",
                match_date=date(2026, 3, 6),
                match_time=time(20, 0),
                kickoff_datetime=datetime(2026, 3, 6, 20, 0, tzinfo=timezone.utc),
                home_team_id=baleares.id,
                away_team_id=reus.id,
                home_team_raw="CD Atlético Baleares",
                away_team_raw="Reus FC Reddis",
                home_score=3,
                away_score=0,
                status="finished",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="segunda-match-3",
                extra_data=None,
            ),
            Match(
                external_id="segunda-m4",
                source_name="futbolme",
                source_url="https://example.com/segunda/m4",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                round_name="Jornada 27",
                raw_match_date="sabado, 14 de marzo de 2026",
                raw_match_time="16:00",
                match_date=date(2026, 3, 14),
                match_time=time(16, 0),
                kickoff_datetime=datetime(2026, 3, 14, 16, 0, tzinfo=timezone.utc),
                home_team_id=porreres.id,
                away_team_id=sant_andreu.id,
                home_team_raw="UE Porreres",
                away_team_raw="UE Sant Andreu",
                home_score=None,
                away_score=None,
                status="scheduled",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="segunda-match-4",
                extra_data=None,
            ),
            Match(
                external_id="segunda-m5",
                source_name="futbolme",
                source_url="https://example.com/segunda/m5",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                round_name="Jornada 27",
                raw_match_date="sabado, 14 de marzo de 2026",
                raw_match_time="18:00",
                match_date=date(2026, 3, 14),
                match_time=time(18, 0),
                kickoff_datetime=datetime(2026, 3, 14, 18, 0, tzinfo=timezone.utc),
                home_team_id=sant_andreu.id,
                away_team_id=reus.id,
                home_team_raw="UE Sant Andreu",
                away_team_raw="Reus FC Reddis",
                home_score=None,
                away_score=None,
                status="scheduled",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="segunda-match-5",
                extra_data=None,
            ),
        ]
    )
    session.commit()


def seed_primera_rfef_with_ud_ibiza(session: Session) -> None:
    competition = Competition(
        code="primera_rfef_baleares",
        name="Primera Federacion Grupo 2",
        normalized_name="primera federacion grupo 2",
        category_level=3,
        gender="male",
        region="Spain",
        country="Spain",
        federation="RFEF",
        source_name="futbolme",
        source_competition_id="3056",
    )
    ibiza = Team(name="UD Ibiza", normalized_name="ud ibiza", gender="male")
    sabadell = Team(name="CE Sabadell FC", normalized_name="ce sabadell fc", gender="male")
    ceuta = Team(name="AD Ceuta FC", normalized_name="ad ceuta fc", gender="male")
    marbella = Team(name="Marbella FC", normalized_name="marbella fc", gender="male")
    session.add_all([competition, ibiza, sabadell, ceuta, marbella])
    session.flush()

    scraped_at = datetime(2026, 3, 28, 10, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            Standing(
                source_name="futbolme",
                source_url="https://example.com/primera/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 2",
                position=1,
                team_id=sabadell.id,
                team_raw="CE Sabadell FC",
                played=29,
                wins=16,
                draws=6,
                losses=7,
                goals_for=40,
                goals_against=23,
                goal_difference=17,
                points=54,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="primera-standing-1",
                extra_data=None,
            ),
            Standing(
                source_name="futbolme",
                source_url="https://example.com/primera/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 2",
                position=12,
                team_id=ceuta.id,
                team_raw="AD Ceuta FC",
                played=29,
                wins=10,
                draws=9,
                losses=10,
                goals_for=31,
                goals_against=30,
                goal_difference=1,
                points=39,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="primera-standing-2",
                extra_data=None,
            ),
            Standing(
                source_name="futbolme",
                source_url="https://example.com/primera/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 2",
                position=13,
                team_id=ibiza.id,
                team_raw="UD Ibiza",
                played=29,
                wins=10,
                draws=8,
                losses=11,
                goals_for=28,
                goals_against=30,
                goal_difference=-2,
                points=38,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="primera-standing-3",
                extra_data=None,
            ),
            Standing(
                source_name="futbolme",
                source_url="https://example.com/primera/standings",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 2",
                position=17,
                team_id=marbella.id,
                team_raw="Marbella FC",
                played=29,
                wins=8,
                draws=8,
                losses=13,
                goals_for=25,
                goals_against=35,
                goal_difference=-10,
                points=32,
                form_text=None,
                scraped_at=scraped_at,
                content_hash="primera-standing-4",
                extra_data=None,
            ),
        ]
    )

    session.add_all(
        [
            Match(
                external_id="primera-m1",
                source_name="futbolme",
                source_url="https://example.com/primera/m1",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 2",
                round_name="Jornada 29",
                raw_match_date="domingo, 22 de marzo de 2026",
                raw_match_time="12:00",
                match_date=date(2026, 3, 22),
                match_time=time(12, 0),
                kickoff_datetime=datetime(2026, 3, 22, 12, 0, tzinfo=timezone.utc),
                home_team_id=ibiza.id,
                away_team_id=ceuta.id,
                home_team_raw="UD Ibiza",
                away_team_raw="AD Ceuta FC",
                home_score=1,
                away_score=0,
                status="finished",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="primera-match-1",
                extra_data=None,
            ),
            Match(
                external_id="primera-m2",
                source_name="futbolme",
                source_url="https://example.com/primera/m2",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 2",
                round_name="Jornada 29",
                raw_match_date="domingo, 22 de marzo de 2026",
                raw_match_time="18:00",
                match_date=date(2026, 3, 22),
                match_time=time(18, 0),
                kickoff_datetime=datetime(2026, 3, 22, 18, 0, tzinfo=timezone.utc),
                home_team_id=sabadell.id,
                away_team_id=marbella.id,
                home_team_raw="CE Sabadell FC",
                away_team_raw="Marbella FC",
                home_score=2,
                away_score=1,
                status="finished",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="primera-match-2",
                extra_data=None,
            ),
            Match(
                external_id="primera-m3",
                source_name="futbolme",
                source_url="https://example.com/primera/m3",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 2",
                round_name="Jornada 30",
                raw_match_date="domingo, 29 de marzo de 2026",
                raw_match_time="12:00",
                match_date=date(2026, 3, 29),
                match_time=time(12, 0),
                kickoff_datetime=datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc),
                home_team_id=marbella.id,
                away_team_id=ibiza.id,
                home_team_raw="Marbella FC",
                away_team_raw="UD Ibiza",
                home_score=None,
                away_score=None,
                status="scheduled",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="primera-match-3",
                extra_data=None,
            ),
            Match(
                external_id="primera-m4",
                source_name="futbolme",
                source_url="https://example.com/primera/m4",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 2",
                round_name="Jornada 30",
                raw_match_date="domingo, 29 de marzo de 2026",
                raw_match_time="18:00",
                match_date=date(2026, 3, 29),
                match_time=time(18, 0),
                kickoff_datetime=datetime(2026, 3, 29, 18, 0, tzinfo=timezone.utc),
                home_team_id=sabadell.id,
                away_team_id=ceuta.id,
                home_team_raw="CE Sabadell FC",
                away_team_raw="AD Ceuta FC",
                home_score=None,
                away_score=None,
                status="scheduled",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=scraped_at,
                content_hash="primera-match-4",
                extra_data=None,
            ),
        ]
    )
    session.commit()


def test_competition_query_service_returns_standings_rankings_and_summary() -> None:
    session = build_session()
    try:
        seed_competition_data(session)
        service = CompetitionQueryService(session)

        standings = service.current_standings("division_honor_mallorca")
        summary = service.summary("division_honor_mallorca")
        top_attack = service.top_scoring_teams("division_honor_mallorca", limit=2)
        top_defense = service.best_defense_teams("division_honor_mallorca", limit=2)
        most_wins = service.most_wins_teams("division_honor_mallorca", limit=2)

        assert standings[0].team == "CE Andratx B"
        assert standings[1].points == 47
        assert summary.total_teams == 3
        assert summary.total_matches == 4
        assert summary.played_matches == 1
        assert summary.pending_matches == 3
        assert top_attack[0].team == "CE Andratx B"
        assert top_attack[0].value == 50
        assert top_defense[0].team == "CE Sineu"
        assert top_defense[0].value == 19
        assert most_wins[0].team == "CE Andratx B"
        assert most_wins[0].value == 17
    finally:
        session.close()


def test_competition_query_service_returns_results_upcoming_and_round_matches() -> None:
    session = build_session()
    try:
        seed_competition_data(session)
        service = CompetitionQueryService(session)

        latest_results = service.latest_results("division_honor_mallorca", limit=3)
        upcoming = service.upcoming_matches("division_honor_mallorca", limit=2)
        round_matches = service.matches_by_round("division_honor_mallorca", round_name="25")

        assert len(latest_results) == 1
        assert latest_results[0].home_score == 2
        assert latest_results[0].away_score == 1
        assert latest_results[0].match_date_raw == "sabado, 07 de marzo de 2026"
        assert upcoming[0].round_name == "Jornada 25"
        assert upcoming[0].status == "scheduled"
        assert upcoming[0].match_time_raw == "16:00"
        assert len(round_matches) == 2
        assert round_matches[0].home_team == "CE Andratx B"
    finally:
        session.close()


def test_competition_query_service_returns_relative_match_windows() -> None:
    session = build_session()
    try:
        seed_competition_data(session)
        service = CompetitionQueryService(session)

        today = service.matches_in_window(
            "division_honor_mallorca",
            window=MatchWindow.TODAY,
            reference_date=date(2026, 3, 14),
        )
        tomorrow = service.matches_in_window(
            "division_honor_mallorca",
            window=MatchWindow.TOMORROW,
            reference_date=date(2026, 3, 14),
        )
        next_weekend = service.matches_in_window(
            "division_honor_mallorca",
            window=MatchWindow.NEXT_WEEKEND,
            reference_date=date(2026, 3, 14),
        )

        assert today.start_date.isoformat() == "2026-03-14"
        assert len(today.matches) == 1
        assert len(tomorrow.matches) == 1
        assert next_weekend.start_date.isoformat() == "2026-03-21"
        assert next_weekend.end_date.isoformat() == "2026-03-22"
        assert len(next_weekend.matches) == 1
        assert next_weekend.matches[0].round_name == "Jornada 26"
    finally:
        session.close()


def test_competition_query_service_filters_relevant_matches_for_tracked_teams() -> None:
    session = build_session()
    try:
        seed_group_with_tracked_teams(session)
        service = CompetitionQueryService(session)

        latest_results = service.latest_results(
            "segunda_rfef_g3_baleares",
            limit=3,
            relevant_only=True,
        )
        upcoming = service.upcoming_matches(
            "segunda_rfef_g3_baleares",
            limit=3,
            relevant_only=True,
        )
        round_matches = service.matches_by_round(
            "segunda_rfef_g3_baleares",
            round_name="27",
            relevant_only=True,
        )
        today = service.matches_in_window(
            "segunda_rfef_g3_baleares",
            window=MatchWindow.TODAY,
            reference_date=date(2026, 3, 14),
            relevant_only=True,
        )

        assert [row.home_team for row in latest_results] == [
            "UD Poblense",
            "CD Atlético Baleares",
        ]
        assert len(upcoming) == 1
        assert upcoming[0].home_team == "UE Porreres"
        assert len(round_matches) == 1
        assert round_matches[0].away_team == "UE Sant Andreu"
        assert len(today.matches) == 1
        assert today.matches[0].home_team == "UE Porreres"
        assert service.relevant_matches_count("segunda_rfef_g3_baleares") == 3
        assert service.tracked_teams("segunda_rfef_g3_baleares") == [
            "UD Poblense",
            "Atletico Baleares",
            "CD Ibiza Islas Pitiusas",
            "CE Andratx",
            "UE Porreres",
        ]
    finally:
        session.close()


def test_competition_query_service_filters_primera_rfef_to_ud_ibiza() -> None:
    session = build_session()
    try:
        seed_primera_rfef_with_ud_ibiza(session)
        service = CompetitionQueryService(session)

        latest_results = service.latest_results(
            "primera_rfef_baleares",
            limit=5,
            relevant_only=True,
        )
        upcoming = service.upcoming_matches(
            "primera_rfef_baleares",
            limit=5,
            relevant_only=True,
        )
        round_matches = service.matches_by_round(
            "primera_rfef_baleares",
            round_name="30",
            relevant_only=True,
        )

        assert [row.home_team for row in latest_results] == ["UD Ibiza"]
        assert len(upcoming) == 1
        assert upcoming[0].away_team == "UD Ibiza"
        assert len(round_matches) == 1
        assert round_matches[0].away_team == "UD Ibiza"
        assert service.tracked_teams("primera_rfef_baleares") == ["UD Ibiza"]
        assert service.relevant_matches_count("primera_rfef_baleares") == 2
    finally:
        session.close()


def test_competition_query_service_editorial_upcoming_matches_stays_on_immediate_round() -> None:
    session = build_session()
    try:
        seed_primera_rfef_with_ud_ibiza(session)
        competition = session.scalar(select(Competition).where(Competition.code == "primera_rfef_baleares"))
        ibiza = session.scalar(select(Team).where(Team.name == "UD Ibiza"))
        ceuta = session.scalar(select(Team).where(Team.name == "AD Ceuta FC"))
        sabadell = session.scalar(select(Team).where(Team.name == "CE Sabadell FC"))
        assert competition is not None
        assert ibiza is not None
        assert ceuta is not None
        assert sabadell is not None

        session.add_all(
            [
                Match(
                    external_id="primera-m5",
                    source_name="futbolme",
                    source_url="https://example.com/primera/m5",
                    competition_id=competition.id,
                    season="2025-26",
                    group_name="Grupo 2",
                    round_name="Jornada 31",
                    raw_match_date="viernes, 03 de abril de 2026",
                    raw_match_time="12:00",
                    match_date=date(2026, 4, 3),
                    match_time=time(12, 0),
                    kickoff_datetime=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                    home_team_id=sabadell.id,
                    away_team_id=ibiza.id,
                    home_team_raw="CE Sabadell FC",
                    away_team_raw="UD Ibiza",
                    home_score=None,
                    away_score=None,
                    status="scheduled",
                    venue=None,
                    has_lineups=False,
                    has_scorers=False,
                    scraped_at=datetime(2026, 3, 31, 10, 0, tzinfo=timezone.utc),
                    content_hash="primera-match-5",
                    extra_data=None,
                ),
                Match(
                    external_id="primera-m6",
                    source_name="futbolme",
                    source_url="https://example.com/primera/m6",
                    competition_id=competition.id,
                    season="2025-26",
                    group_name="Grupo 2",
                    round_name="Jornada 32",
                    raw_match_date="domingo, 12 de abril de 2026",
                    raw_match_time="12:00",
                    match_date=date(2026, 4, 12),
                    match_time=time(12, 0),
                    kickoff_datetime=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
                    home_team_id=ibiza.id,
                    away_team_id=ceuta.id,
                    home_team_raw="UD Ibiza",
                    away_team_raw="AD Ceuta FC",
                    home_score=None,
                    away_score=None,
                    status="scheduled",
                    venue=None,
                    has_lineups=False,
                    has_scorers=False,
                    scraped_at=datetime(2026, 3, 31, 10, 0, tzinfo=timezone.utc),
                    content_hash="primera-match-6",
                    extra_data=None,
                ),
            ]
        )
        session.commit()

        service = CompetitionQueryService(session)
        upcoming = service.editorial_upcoming_matches(
            "primera_rfef_baleares",
            limit=5,
            relevant_only=True,
            reference_date=date(2026, 3, 31),
        )

        assert len(upcoming) == 1
        assert upcoming[0].round_name == "Jornada 31"
        assert upcoming[0].away_team == "UD Ibiza"
    finally:
        session.close()
