from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import select

from app.core.enums import ContentType
from app.core.match_importance import MatchImportanceConfig, MatchImportanceWeights
from app.db.models import Competition, ContentCandidate, Match, Team
from app.services.match_importance import MatchImportanceService
from tests.unit.services.test_editorial_narratives import build_session, seed_competition
from tests.unit.services.test_team_form import seed_form_data


def add_scheduled_match(
    session,
    *,
    competition_code: str,
    external_id: str,
    match_date: date,
    match_time: time,
    home_team: str,
    away_team: str,
) -> None:
    competition = session.scalar(select(Competition).where(Competition.code == competition_code))
    assert competition is not None
    home = session.scalar(select(Team).where(Team.name == home_team))
    away = session.scalar(select(Team).where(Team.name == away_team))
    assert home is not None and away is not None
    session.add(
        Match(
            external_id=external_id,
            source_name="futbolme",
            source_url=f"https://example.com/{competition_code}/{external_id}",
            competition_id=competition.id,
            season="2025-26",
            group_name="Grupo test",
            round_name="Jornada 27",
            raw_match_date=match_date.isoformat(),
            raw_match_time=match_time.strftime("%H:%M"),
            match_date=match_date,
            match_time=match_time,
            kickoff_datetime=datetime.combine(match_date, match_time, tzinfo=timezone.utc),
            home_team_id=home.id,
            away_team_id=away.id,
            home_team_raw=home_team,
            away_team_raw=away_team,
            home_score=None,
            away_score=None,
            status="scheduled",
            venue=None,
            has_lineups=False,
            has_scorers=False,
            scraped_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
            content_hash=f"{competition_code}-{external_id}",
            extra_data=None,
        )
    )
    session.commit()


def importance_config() -> dict[str, MatchImportanceConfig]:
    return {
        "default": MatchImportanceConfig(),
        "tercera_rfef_g11": MatchImportanceConfig(
            top_zone_positions=[1, 2, 3, 4],
            playoff_positions=[2, 3, 4],
            bottom_zone_positions=[5, 6, 7],
            direct_rival_gap_max=2,
            near_playoff_margin=1,
            near_bottom_margin=1,
            hot_form_points_threshold=10,
            cold_form_points_threshold=4,
            weights=MatchImportanceWeights(
                title_race=28,
                top_table_match=18,
                playoff_clash=18,
                relegation_clash=18,
                direct_rivalry=14,
                hot_form_match=14,
                cold_form_match=8,
            ),
        ),
    }


def seed_second_competition(session) -> None:
    seed_competition(
        session,
        code="segunda_rfef_g3_baleares",
        name="2a RFEF Grupo 3",
        teams=["Torrent CF", "UE Porreres", "UD Poblense", "Atletico Baleares"],
        standings_rows=[
            {"position": 1, "team": "UD Poblense", "played": 27, "wins": 15, "draws": 6, "losses": 6, "goals_for": 35, "goals_against": 20, "goal_difference": 15, "points": 51},
            {"position": 2, "team": "Atletico Baleares", "played": 27, "wins": 14, "draws": 6, "losses": 7, "goals_for": 34, "goals_against": 24, "goal_difference": 10, "points": 48},
            {"position": 3, "team": "Torrent CF", "played": 27, "wins": 10, "draws": 8, "losses": 9, "goals_for": 25, "goals_against": 23, "goal_difference": 2, "points": 38},
            {"position": 4, "team": "UE Porreres", "played": 27, "wins": 9, "draws": 8, "losses": 10, "goals_for": 22, "goals_against": 26, "goal_difference": -4, "points": 35},
        ],
        match_rows=[],
    )


def test_match_importance_scores_and_tags_top_match_correctly() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="top-clash",
            match_date=date(2026, 3, 21),
            match_time=time(18, 0),
            home_team="CE Alpha",
            away_team="CE Beta",
        )
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="playoff-clash",
            match_date=date(2026, 3, 21),
            match_time=time(18, 30),
            home_team="CE Gamma",
            away_team="CE Delta",
        )
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="relegation-clash",
            match_date=date(2026, 3, 21),
            match_time=time(19, 0),
            home_team="CE Epsilon",
            away_team="CE Foxtrot",
        )

        result = MatchImportanceService(session, config_map=importance_config()).top_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
            limit=3,
        )

        top = result.rows[0]
        assert (top.home_team, top.away_team) == ("CE Alpha", "CE Beta")
        assert top.importance_score == 92
        assert top.tags == [
            "title_race",
            "top_table_match",
            "playoff_clash",
            "direct_rivalry",
            "hot_form_match",
        ]
    finally:
        session.close()


def test_match_importance_does_not_mix_competitions() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        seed_second_competition(session)
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="top-clash",
            match_date=date(2026, 3, 21),
            match_time=time(18, 0),
            home_team="CE Alpha",
            away_team="CE Beta",
        )
        add_scheduled_match(
            session,
            competition_code="segunda_rfef_g3_baleares",
            external_id="segunda-clash",
            match_date=date(2026, 3, 21),
            match_time=time(18, 0),
            home_team="Torrent CF",
            away_team="UE Porreres",
        )

        result = MatchImportanceService(session, config_map=importance_config()).show_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )

        assert result.rows
        assert all(row.competition_slug == "tercera_rfef_g11" for row in result.rows)
        assert all("Torrent CF" not in {row.home_team, row.away_team} for row in result.rows)
    finally:
        session.close()


def test_match_importance_generate_persists_featured_match_candidates() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="top-clash",
            match_date=date(2026, 3, 21),
            match_time=time(18, 0),
            home_team="CE Alpha",
            away_team="CE Beta",
        )
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="playoff-clash",
            match_date=date(2026, 3, 21),
            match_time=time(18, 30),
            home_team="CE Gamma",
            away_team="CE Delta",
        )
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="relegation-clash",
            match_date=date(2026, 3, 21),
            match_time=time(19, 0),
            home_team="CE Epsilon",
            away_team="CE Foxtrot",
        )

        result = MatchImportanceService(session, config_map=importance_config()).generate_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
            limit=3,
        )
        session.commit()

        rows = session.execute(select(ContentCandidate).order_by(ContentCandidate.id.asc())).scalars().all()

        assert result.stats.found == 6
        assert result.stats.inserted == 6
        assert {row.content_type for row in rows} == {
            str(ContentType.FEATURED_MATCH_PREVIEW),
            str(ContentType.FEATURED_MATCH_EVENT),
        }
        preview = next(row for row in rows if row.content_type == str(ContentType.FEATURED_MATCH_PREVIEW))
        assert "CE Alpha vs CE Beta" in preview.text_draft
    finally:
        session.close()
