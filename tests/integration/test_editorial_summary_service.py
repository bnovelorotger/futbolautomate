from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import Competition, Match, News, Standing, Team
from app.services.editorial_summary import CompetitionEditorialSummaryService
from app.services.news_editorial import enrich_news_editorial


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
                round_name="Jornada 24",
                raw_match_date="domingo, 08 de marzo de 2026",
                raw_match_time="12:00",
                match_date=date(2026, 3, 8),
                match_time=time(12, 0),
                kickoff_datetime=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                home_team_id=team_c.id,
                away_team_id=team_a.id,
                home_team_raw="CD Ferriolense",
                away_team_raw="CE Andratx B",
                home_score=1,
                away_score=2,
                status="finished",
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
                content_hash="match-4",
                extra_data=None,
            ),
            Match(
                external_id="m5",
                source_name="futbolme",
                source_url="https://example.com/m5",
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
                content_hash="match-5",
                extra_data=None,
            ),
        ]
    )
    session.commit()


def seed_news(session: Session) -> None:
    scraped_at = datetime(2026, 3, 14, 9, 30, tzinfo=timezone.utc)
    session.add_all(
        [
            News(
                source_name="diario_mallorca",
                source_url="https://example.com/direct-competition",
                title="La Division Honor Mallorca entra en una jornada decisiva",
                subtitle=None,
                published_at=datetime(2026, 3, 14, 8, 30, tzinfo=timezone.utc),
                summary="La categoria mallorquina afronta un fin de semana clave.",
                body_text=None,
                news_type="other",
                clubs_detected=[],
                competition_detected=None,
                raw_category="Deportes",
                scraped_at=scraped_at,
                content_hash="news-1",
            ),
            News(
                source_name="diario_mallorca",
                source_url="https://example.com/club-overlap",
                title="CE Andratx B defiende el liderato este sabado",
                subtitle=None,
                published_at=datetime(2026, 3, 14, 8, 0, tzinfo=timezone.utc),
                summary="El filial afronta una jornada de liga importante.",
                body_text=None,
                news_type="other",
                clubs_detected=[],
                competition_detected=None,
                raw_category="Deportes",
                scraped_at=scraped_at,
                content_hash="news-2",
            ),
            News(
                source_name="ultima_hora",
                source_url="https://example.com/general-context",
                title="El Real Mallorca prepara el duelo ante el Espanyol",
                subtitle=None,
                published_at=datetime(2026, 3, 14, 7, 30, tzinfo=timezone.utc),
                summary="Nueva jornada de liga para el conjunto bermellon.",
                body_text=None,
                news_type="other",
                clubs_detected=[],
                competition_detected=None,
                raw_category="Deportes | Real Mallorca",
                scraped_at=scraped_at,
                content_hash="news-3",
            ),
            News(
                source_name="ultima_hora",
                source_url="https://example.com/other-sport",
                title="El Palma Futsal retoma la competicion europea",
                subtitle=None,
                published_at=datetime(2026, 3, 14, 7, 0, tzinfo=timezone.utc),
                summary="El equipo disputa una nueva jornada continental.",
                body_text=None,
                news_type="other",
                clubs_detected=[],
                competition_detected=None,
                raw_category="Deportes | Palma Futsal",
                scraped_at=scraped_at,
                content_hash="news-4",
            ),
        ]
    )
    session.commit()


def seed_national_group_with_balearic_focus(session: Session) -> None:
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
                content_hash="segunda-summary-standing-1",
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
                content_hash="segunda-summary-standing-2",
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
                content_hash="segunda-summary-standing-3",
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
                content_hash="segunda-summary-standing-4",
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
                content_hash="segunda-summary-standing-5",
                extra_data=None,
            ),
        ]
    )

    session.add_all(
        [
            Match(
                external_id="segunda-summary-m1",
                source_name="futbolme",
                source_url="https://example.com/segunda-summary/m1",
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
                content_hash="segunda-summary-match-1",
                extra_data=None,
            ),
            Match(
                external_id="segunda-summary-m2",
                source_name="futbolme",
                source_url="https://example.com/segunda-summary/m2",
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
                content_hash="segunda-summary-match-2",
                extra_data=None,
            ),
            Match(
                external_id="segunda-summary-m3",
                source_name="futbolme",
                source_url="https://example.com/segunda-summary/m3",
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
                content_hash="segunda-summary-match-3",
                extra_data=None,
            ),
            Match(
                external_id="segunda-summary-m4",
                source_name="futbolme",
                source_url="https://example.com/segunda-summary/m4",
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
                content_hash="segunda-summary-match-4",
                extra_data=None,
            ),
            Match(
                external_id="segunda-summary-m5",
                source_name="futbolme",
                source_url="https://example.com/segunda-summary/m5",
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
                content_hash="segunda-summary-match-5",
                extra_data=None,
            ),
        ]
    )

    news_scraped_at = datetime(2026, 3, 14, 9, 30, tzinfo=timezone.utc)
    session.add_all(
        [
            News(
                source_name="diario_mallorca",
                source_url="https://example.com/segunda-summary/news-1",
                title="El CD Atlético Baleares quiere seguir arriba en Segunda RFEF",
                subtitle=None,
                published_at=datetime(2026, 3, 14, 8, 30, tzinfo=timezone.utc),
                summary="El equipo balear afronta otra jornada exigente del grupo 3.",
                body_text=None,
                news_type="other",
                clubs_detected=[],
                competition_detected=None,
                raw_category="Deportes",
                scraped_at=news_scraped_at,
                content_hash="segunda-summary-news-1",
            ),
            News(
                source_name="ultima_hora",
                source_url="https://example.com/segunda-summary/news-2",
                title="UD Poblense y UE Porreres preparan un fin de semana clave",
                subtitle=None,
                published_at=datetime(2026, 3, 14, 8, 0, tzinfo=timezone.utc),
                summary="Los dos equipos baleares llegan en buena dinamica.",
                body_text=None,
                news_type="other",
                clubs_detected=[],
                competition_detected=None,
                raw_category="Deportes",
                scraped_at=news_scraped_at,
                content_hash="segunda-summary-news-2",
            ),
            News(
                source_name="ultima_hora",
                source_url="https://example.com/segunda-summary/news-3",
                title="El Real Mallorca recibe al Espanyol en Son Moix",
                subtitle=None,
                published_at=datetime(2026, 3, 14, 7, 0, tzinfo=timezone.utc),
                summary="Otra cita relevante para el futbol balear general.",
                body_text=None,
                news_type="other",
                clubs_detected=[],
                competition_detected=None,
                raw_category="Deportes | Real Mallorca",
                scraped_at=news_scraped_at,
                content_hash="segunda-summary-news-3",
            ),
        ]
    )
    session.commit()


def test_competition_editorial_summary_service_combines_competition_and_news() -> None:
    session = build_session()
    try:
        seed_competition_data(session)
        seed_news(session)
        stats = enrich_news_editorial(session)
        session.commit()

        payload = CompetitionEditorialSummaryService(session).build_competition_summary(
            competition_code="division_honor_mallorca",
            reference_date=date(2026, 3, 14),
            results_limit=2,
            upcoming_limit=2,
            news_limit=3,
            standings_limit=3,
        )

        assert stats.found == 4
        assert payload.metadata.competition_slug == "division_honor_mallorca"
        assert payload.competition_state.total_teams == 3
        assert payload.competition_state.total_matches == 5
        assert payload.competition_state.played_matches == 2
        assert payload.competition_state.pending_matches == 3

        assert len(payload.latest_results) == 2
        assert payload.latest_results[0].round_name == "Jornada 24"
        assert len(payload.upcoming_matches) == 2
        assert payload.upcoming_matches[0].match_date.isoformat() == "2026-03-14"

        assert len(payload.current_standings) == 3
        assert payload.current_standings[0].team == "CE Andratx B"
        assert payload.rankings.best_attack is not None
        assert payload.rankings.best_attack.team == "CE Andratx B"
        assert payload.rankings.best_defense is not None
        assert payload.rankings.best_defense.team == "CE Sineu"
        assert payload.rankings.most_wins is not None
        assert payload.rankings.most_wins.team == "CE Andratx B"

        assert len(payload.calendar_windows.today) == 1
        assert len(payload.calendar_windows.tomorrow) == 1
        assert len(payload.calendar_windows.next_weekend) == 1

        assert [item.selection_reason for item in payload.editorial_news] == [
            "competition_detected",
            "club_overlap",
            "general_context",
        ]
        assert payload.editorial_news[0].title == "La Division Honor Mallorca entra en una jornada decisiva"
        assert payload.editorial_news[1].title == "CE Andratx B defiende el liderato este sabado"
        assert payload.editorial_news[2].title == "El Real Mallorca prepara el duelo ante el Espanyol"

        assert payload.aggregate_metrics.total_goals_scored == 6
        assert payload.aggregate_metrics.average_goals_per_played_match == 3.0
        assert payload.aggregate_metrics.relevant_news_count == 3

        serialized = payload.model_dump(mode="json")
        assert serialized["metadata"]["competition_slug"] == "division_honor_mallorca"
        assert serialized["calendar_windows"]["today"][0]["home_team"] == "CE Andratx B"
    finally:
        session.close()


def test_competition_editorial_summary_service_filters_to_tracked_balearic_teams() -> None:
    session = build_session()
    try:
        seed_national_group_with_balearic_focus(session)
        enrich_news_editorial(session)
        session.commit()

        payload = CompetitionEditorialSummaryService(session).build_competition_summary(
            competition_code="segunda_rfef_g3_baleares",
            reference_date=date(2026, 3, 14),
            results_limit=3,
            upcoming_limit=3,
            news_limit=3,
            standings_limit=5,
        )

        assert payload.metadata.competition_slug == "segunda_rfef_g3_baleares"
        assert payload.competition_state.total_teams == 5
        assert payload.competition_state.total_matches == 5
        assert payload.competition_state.played_matches == 3
        assert payload.competition_state.pending_matches == 2

        assert [item.home_team for item in payload.latest_results] == [
            "UD Poblense",
            "CD Atlético Baleares",
        ]
        assert len(payload.upcoming_matches) == 1
        assert payload.upcoming_matches[0].home_team == "UE Porreres"
        assert len(payload.calendar_windows.today) == 1
        assert payload.calendar_windows.today[0].home_team == "UE Porreres"

        assert len(payload.current_standings) == 5
        assert payload.current_standings[0].team == "UE Sant Andreu"
        assert payload.rankings.best_attack is not None
        assert payload.rankings.best_attack.team == "UE Sant Andreu"

        assert payload.editorial_news[0].selection_reason in {"competition_detected", "club_overlap"}
        assert payload.editorial_news[0].title == "El CD Atlético Baleares quiere seguir arriba en Segunda RFEF"
        assert payload.editorial_news[1].selection_reason == "club_overlap"
        assert payload.editorial_news[1].title == "UD Poblense y UE Porreres preparan un fin de semana clave"

        assert payload.aggregate_metrics.total_goals_scored == 7
        assert payload.aggregate_metrics.average_goals_per_played_match == round(7 / 3, 2)
        assert payload.aggregate_metrics.relevant_news_count == 3
    finally:
        session.close()
