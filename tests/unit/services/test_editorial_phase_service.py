from __future__ import annotations

from datetime import date, time

from app.core.enums import ContentType, EditorialSeasonPhase
from app.services.editorial_phase import EditorialPhaseService
from tests.unit.services.test_editorial_narratives import build_session, seed_competition
from tests.unit.services.test_match_importance import add_scheduled_match


def _seed_basic_competition(session, *, code: str, name: str, teams: list[str]) -> None:
    seed_competition(
        session,
        code=code,
        name=name,
        teams=teams,
        standings_rows=[],
        match_rows=[],
    )


def test_regular_competition_enters_playoffs_when_child_playoff_has_future_match() -> None:
    session = build_session()
    try:
        _seed_basic_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Grupo 11",
            teams=["CE Alpha", "CE Beta"],
        )
        _seed_basic_competition(
            session,
            code="tercera_rfef_g11_playoff",
            name="3a RFEF Playoff",
            teams=["CE Alpha", "CE Beta"],
        )
        add_scheduled_match(
            session,
            competition_code="tercera_rfef_g11_playoff",
            external_id="po-future",
            match_date=date(2026, 5, 24),
            match_time=time(18, 0),
            home_team="CE Alpha",
            away_team="CE Beta",
        )

        service = EditorialPhaseService(session)
        regular_state = service.phase_for_competition("tercera_rfef_g11", reference_date=date(2026, 5, 24))
        playoff_state = service.phase_for_competition("tercera_rfef_g11_playoff", reference_date=date(2026, 5, 24))

        assert playoff_state.phase == EditorialSeasonPhase.PLAYOFFS
        assert regular_state.phase == EditorialSeasonPhase.PLAYOFFS
        assert regular_state.reason == "child_playoff_active:tercera_rfef_g11_playoff"
    finally:
        session.close()


def test_stale_playoff_competition_does_not_activate_current_playoff_phase() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="primera_rfef_playoff_ascenso",
            name="Primera RFEF Playoff Ascenso",
            teams=["UD Ibiza", "CE Beta"],
            standings_rows=[],
            match_rows=[
                {
                    "round_name": None,
                    "match_date": date(2025, 6, 22),
                    "match_time": time(18, 0),
                    "home_team": "UD Ibiza",
                    "away_team": "CE Beta",
                    "home_score": 1,
                    "away_score": 0,
                },
            ],
        )

        state = EditorialPhaseService(session).phase_for_competition(
            "primera_rfef_playoff_ascenso",
            reference_date=date(2026, 5, 24),
        )

        assert state.phase == EditorialSeasonPhase.OFFSEASON
        assert state.reason == "playoff_inactive_or_stale"
    finally:
        session.close()


def test_scheduled_match_in_the_past_is_not_regular_active() -> None:
    session = build_session()
    try:
        _seed_basic_competition(
            session,
            code="primera_rfef_baleares",
            name="Primera RFEF Baleares",
            teams=["UD Ibiza", "CE Beta"],
        )
        add_scheduled_match(
            session,
            competition_code="primera_rfef_baleares",
            external_id="overdue",
            match_date=date(2026, 5, 22),
            match_time=time(20, 0),
            home_team="UD Ibiza",
            away_team="CE Beta",
        )

        state = EditorialPhaseService(session).phase_for_competition(
            "primera_rfef_baleares",
            reference_date=date(2026, 5, 24),
        )

        assert state.phase == EditorialSeasonPhase.OFFSEASON
        assert state.future_scheduled_count == 0
        assert state.overdue_scheduled_count == 1
    finally:
        session.close()


def test_recently_finished_playoff_enters_season_wrap() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="division_honor_mallorca_playoff",
            name="Division Honor Mallorca Playoff",
            teams=["CE Alpha", "CE Beta"],
            standings_rows=[],
            match_rows=[
                {
                    "round_name": None,
                    "match_date": date(2026, 5, 23),
                    "match_time": time(19, 0),
                    "home_team": "CE Alpha",
                    "away_team": "CE Beta",
                    "home_score": 2,
                    "away_score": 1,
                },
            ],
        )

        state = EditorialPhaseService(session).phase_for_competition(
            "division_honor_mallorca_playoff",
            reference_date=date(2026, 5, 24),
        )

        assert state.phase == EditorialSeasonPhase.SEASON_WRAP
        assert state.reason == "playoff_recently_finished"
    finally:
        session.close()


def test_phase_content_policy_blocks_regular_ranking_during_playoffs_and_allows_playoff_posts() -> None:
    session = build_session()
    try:
        _seed_basic_competition(
            session,
            code="segunda_rfef_g3_baleares",
            name="2a RFEF Grupo 3",
            teams=["UD Poblense", "CE Beta"],
        )
        _seed_basic_competition(
            session,
            code="segunda_rfef_g3_playoff_ascenso",
            name="2a RFEF Playoff Ascenso",
            teams=["UD Poblense", "CE Beta"],
        )
        add_scheduled_match(
            session,
            competition_code="segunda_rfef_g3_playoff_ascenso",
            external_id="po-future",
            match_date=date(2026, 5, 24),
            match_time=time(18, 0),
            home_team="UD Poblense",
            away_team="CE Beta",
        )

        service = EditorialPhaseService(session)
        regular_allowed, regular_state, regular_reason = service.content_type_allowed(
            "segunda_rfef_g3_baleares",
            ContentType.RANKING,
            reference_date=date(2026, 5, 24),
        )
        playoff_results_allowed, _, _ = service.content_type_allowed(
            "segunda_rfef_g3_playoff_ascenso",
            ContentType.RESULTS_ROUNDUP,
            reference_date=date(2026, 5, 24),
        )
        playoff_preview_allowed, _, _ = service.content_type_allowed(
            "segunda_rfef_g3_playoff_ascenso",
            ContentType.FEATURED_MATCH_PREVIEW,
            reference_date=date(2026, 5, 24),
        )
        playoff_bracket_allowed, _, _ = service.content_type_allowed(
            "segunda_rfef_g3_playoff_ascenso",
            ContentType.PLAYOFF_BRACKET,
            reference_date=date(2026, 5, 24),
        )

        assert regular_state.phase == EditorialSeasonPhase.PLAYOFFS
        assert regular_allowed is False
        assert regular_reason == "phase_content_type_blocked:playoffs:ranking"
        assert playoff_results_allowed is True
        assert playoff_preview_allowed is True
        assert playoff_bracket_allowed is True
    finally:
        session.close()


def test_season_wrap_allows_wrap_stats_and_outcomes_for_regular_competition() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="primera_rfef_baleares",
            name="Primera RFEF Baleares",
            teams=["UD Ibiza", "CE Beta"],
            standings_rows=[],
            match_rows=[
                {
                    "round_name": "Jornada 38",
                    "match_date": date(2026, 5, 22),
                    "match_time": time(20, 0),
                    "home_team": "UD Ibiza",
                    "away_team": "CE Beta",
                    "home_score": 2,
                    "away_score": 0,
                },
            ],
        )

        service = EditorialPhaseService(session)
        stats_allowed, state, _ = service.content_type_allowed(
            "primera_rfef_baleares",
            ContentType.SEASON_WRAP_STATS,
            reference_date=date(2026, 5, 24),
        )
        outcomes_allowed, _, _ = service.content_type_allowed(
            "primera_rfef_baleares",
            ContentType.SEASON_WRAP_OUTCOMES,
            reference_date=date(2026, 5, 24),
        )

        assert state.phase == EditorialSeasonPhase.SEASON_WRAP
        assert stats_allowed is True
        assert outcomes_allowed is True
    finally:
        session.close()
