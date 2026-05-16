from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import select

from app.core.standings_zones import CompetitionStandingsZones
from app.db.models import Competition, Match, Team
from app.services.featured_match_preview_generator import FeaturedMatchPreviewGenerator
from app.services.match_zone_calculator import MatchZoneCalculator
from tests.unit.services.test_editorial_narratives import build_session
from tests.unit.services.test_match_importance import add_scheduled_match
from tests.unit.services.test_team_form import seed_form_data


def _competition_id(session, competition_code: str) -> int:
    competition = session.scalar(select(Competition).where(Competition.code == competition_code))
    assert competition is not None
    return competition.id


def _team_id(session, team_name: str) -> int:
    team = session.scalar(select(Team).where(Team.name == team_name))
    assert team is not None
    return team.id


def _add_finished_h2h_match(
    session,
    *,
    competition_code: str,
    external_id: str,
    season: str,
    match_date: date,
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
) -> None:
    competition_id = _competition_id(session, competition_code)
    session.add(
        Match(
            external_id=external_id,
            source_name="futbolme",
            source_url=f"https://example.com/{competition_code}/{external_id}",
            competition_id=competition_id,
            season=season,
            group_name="Grupo test",
            round_name="H2H",
            raw_match_date=match_date.isoformat(),
            raw_match_time="18:00",
            match_date=match_date,
            match_time=time(18, 0),
            kickoff_datetime=datetime.combine(match_date, time(18, 0), tzinfo=timezone.utc),
            home_team_id=_team_id(session, home_team),
            away_team_id=_team_id(session, away_team),
            home_team_raw=home_team,
            away_team_raw=away_team,
            home_score=home_score,
            away_score=away_score,
            status="finished",
            venue=None,
            has_lineups=False,
            has_scorers=False,
            scraped_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
            content_hash=f"{competition_code}-{external_id}",
            extra_data=None,
        )
    )
    session.commit()


def test_featured_match_preview_generator_builds_enriched_payload() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="featured-preview",
            match_date=date(2026, 3, 21),
            match_time=time(18, 0),
            home_team="CE Epsilon",
            away_team="CE Delta",
        )
        _add_finished_h2h_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="h2h-2025",
            season="2025-26",
            match_date=date(2025, 11, 2),
            home_team="CE Delta",
            away_team="CE Epsilon",
            home_score=1,
            away_score=0,
        )
        _add_finished_h2h_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="h2h-2024",
            season="2024-25",
            match_date=date(2025, 4, 14),
            home_team="CE Epsilon",
            away_team="CE Delta",
            home_score=1,
            away_score=0,
        )
        _add_finished_h2h_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="h2h-2023",
            season="2023-24",
            match_date=date(2024, 2, 12),
            home_team="CE Delta",
            away_team="CE Epsilon",
            home_score=2,
            away_score=2,
        )
        _add_finished_h2h_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="h2h-2022",
            season="2022-23",
            match_date=date(2023, 2, 5),
            home_team="CE Epsilon",
            away_team="CE Delta",
            home_score=3,
            away_score=0,
        )

        service = FeaturedMatchPreviewGenerator(
            session,
            zone_calculator=MatchZoneCalculator(
                zones={
                    "tercera_rfef_g11": CompetitionStandingsZones(
                        playoff_positions=[2, 3, 4],
                        relegation_positions=[7],
                    )
                }
            ),
        )
        preview = service.preview_for_competition(
            "tercera_rfef_g11",
            reference_date=date(2026, 3, 16),
        )

        assert preview is not None
        assert preview.featured_match.home_team == "CE Epsilon"
        assert preview.featured_match.away_team == "CE Delta"
        assert preview.home_form is not None
        assert preview.away_form is not None
        assert preview.home_analytics is not None
        assert preview.away_analytics is not None
        assert preview.home_form.sequence == "LLLWD"
        assert preview.home_form.points == 4
        assert preview.away_form.sequence == "LLLDD"
        assert preview.away_form.points == 2
        assert preview.home_analytics.recent_trend.recent_points_per_game == 0.8
        assert preview.away_analytics.season_pace.projected_final_points == 33.0
        assert preview.zone_context.home_team.current.gaps.points_to_playoff == 2
        assert preview.zone_context.home_team.win_scenario.simulated_zone == "playoff"
        assert preview.zone_context.home_team.win_scenario.implication == "Una victoria lo meteria en playoff"

        h2h = preview.head_to_head
        assert h2h.matches_played == 4
        assert h2h.seasons == ["2025-26", "2024-25", "2023-24"]
        assert h2h.home_team.team == "CE Epsilon"
        assert h2h.home_team.wins == 1
        assert h2h.home_team.draws == 2
        assert h2h.home_team.losses == 1
        assert h2h.home_team.avg_goals_for == 0.75
        assert h2h.home_team.avg_goals_against == 0.75

        payload = preview.to_source_payload()
        assert payload["form_window"] == 5
        assert payload["teams"] == ["CE Epsilon", "CE Delta"]
        assert payload["home_form"] is not None
        assert payload["away_form"] is not None
        assert payload["home_analytics"] is not None
        assert payload["away_analytics"] is not None
        assert payload["head_to_head"]["matches_played"] == 4
        assert payload["zone_context"]["home_team"]["win_scenario"]["simulated_zone"] == "playoff"
        assert any("Tendencia PPG" in hook for hook in payload["editorial_hooks"])
        assert any("Ritmo de temporada" in hook for hook in payload["editorial_hooks"])
        assert any("H2H ultimos 4" in hook for hook in payload["editorial_hooks"])
        assert any("CE Epsilon: Una victoria lo meteria en playoff." in hook for hook in payload["editorial_hooks"])
    finally:
        session.close()


def test_featured_match_preview_generator_build_source_payload_for_explicit_match() -> None:
    session = build_session()
    try:
        seed_form_data(session)
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11",
            external_id="featured-explicit",
            match_date=date(2026, 3, 21),
            match_time=time(20, 0),
            home_team="CE Beta",
            away_team="CE Alpha",
        )

        service = FeaturedMatchPreviewGenerator(session)
        match = service.queries.editorial_upcoming_matches(
            "tercera_rfef_g11",
            limit=1,
            relevant_only=True,
            reference_date=date(2026, 3, 16),
        )[0]
        payload = service.build_source_payload(
            "tercera_rfef_g11",
            featured_match=match,
            matches=[match],
            reference_date=date(2026, 3, 16),
        )

        assert payload["featured_match"]["home_team"] == "CE Beta"
        assert payload["home_analytics"]["team"] == "CE Beta"
        assert payload["zone_context"]["home_team"]["win_scenario"]["simulated_zone"] == "leader"
        assert payload["zone_context"]["home_team"]["win_scenario"]["implication"] == "Una victoria lo llevaria al liderato"
    finally:
        session.close()
