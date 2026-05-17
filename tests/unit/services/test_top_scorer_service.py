from __future__ import annotations

from datetime import date, datetime, time, timezone
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from app.core.enums import ContentCandidateStatus, ContentType
from app.db.models import Competition, ContentCandidate, Match, MatchEvent, Team
from app.services.top_scorer_service import TopScorerService
from app.services.top_scorer_tracker import (
    MIN_TOP_SCORER_GOAL_EVENTS,
    MIN_TOP_SCORER_LEADER_GOALS,
)
from tests.unit.services.test_editorial_narratives import build_session


def _seed_competition(session) -> Competition:
    competition = Competition(
        code="tercera_rfef_g11",
        name="3a RFEF Grupo 11",
        normalized_name="tercera-rfef-g11",
        category_level=4,
        gender="male",
        region="Baleares",
        country="Spain",
        federation="RFEF",
        source_name="futbolme",
        source_competition_id="3047",
    )
    session.add(competition)
    session.flush()
    return competition


def _seed_teams(session) -> tuple[Team, Team, Team]:
    alpha = Team(name="CE Alpha", normalized_name="ce-alpha", gender="male")
    beta = Team(name="CE Beta", normalized_name="ce-beta", gender="male")
    gamma = Team(name="CE Gamma", normalized_name="ce-gamma", gender="male")
    session.add_all([alpha, beta, gamma])
    session.flush()
    return alpha, beta, gamma


def _seed_match(session, competition_id: int, home_team: Team, away_team: Team, *, external_id: str, has_scorers: bool = True) -> Match:
    match = Match(
        external_id=external_id,
        source_name="futbolme",
        source_url=f"https://example.com/{external_id}",
        competition_id=competition_id,
        season="2025-26",
        group_name="Grupo test",
        round_name="Jornada 25",
        raw_match_date="2026-03-15",
        raw_match_time="18:00",
        match_date=date(2026, 3, 15),
        match_time=time(18, 0),
        kickoff_datetime=datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc),
        home_team_id=home_team.id,
        away_team_id=away_team.id,
        home_team_raw=home_team.name,
        away_team_raw=away_team.name,
        home_score=3,
        away_score=0,
        status="finished",
        venue=None,
        has_lineups=False,
        has_scorers=has_scorers,
        scraped_at=datetime(2026, 3, 15, 21, 0, tzinfo=timezone.utc),
        content_hash=external_id,
        extra_data={},
    )
    session.add(match)
    session.flush()
    return match


def _seed_goal(
    session,
    match: Match,
    team: Team,
    *,
    player: str,
    sort_order: int,
    event_key: str,
    team_side: str = "home",
) -> MatchEvent:
    event = MatchEvent(
        match_id=match.id,
        team_id=team.id,
        team_side=team_side,
        event_type="goal",
        period="Primer Tiempo",
        minute_raw="10",
        minute=10,
        minute_extra=None,
        player_raw=player,
        player_source_url=None,
        sort_order=sort_order,
        source_event_key=event_key,
        raw_payload={},
    )
    session.add(event)
    session.flush()
    return event


def _seed_enough_data(session) -> tuple[Competition, Team]:
    """Seed data that meets the MIN thresholds for candidate generation.

    Uses only home matches for alpha so that (player, team) keys are stable
    across both covered matches — the tracker groups by (player_raw, team_raw).
    """
    competition = _seed_competition(session)
    alpha, beta, gamma = _seed_teams(session)

    # alpha is home in both matches so Nando's team_raw is always "CE Alpha"
    m1 = _seed_match(session, competition.id, alpha, beta, external_id="m1")
    m2 = _seed_match(session, competition.id, alpha, gamma, external_id="m2")

    # Nando scores MIN_TOP_SCORER_LEADER_GOALS goals for alpha (home) across two matches
    for index in range(MIN_TOP_SCORER_LEADER_GOALS):
        match = m1 if index < 2 else m2
        _seed_goal(
            session,
            match,
            alpha,
            player="Nando",
            sort_order=index + 1,
            event_key=f"g-nando-{index}",
            team_side="home",
        )

    # Extra goals so total >= MIN_TOP_SCORER_GOAL_EVENTS
    remaining = max(0, MIN_TOP_SCORER_GOAL_EVENTS - MIN_TOP_SCORER_LEADER_GOALS)
    for index in range(remaining):
        _seed_goal(
            session,
            m1,
            beta,
            player="Nico",
            sort_order=10 + index,
            event_key=f"g-nico-{index}",
            team_side="away",
        )

    session.commit()
    return competition, alpha


def test_generate_produces_candidate_with_correct_text() -> None:
    session = build_session()
    try:
        _seed_enough_data(session)

        # Patch catalog so editorial_name is predictable
        mock_definition = MagicMock()
        mock_definition.editorial_name = "3a RFEF Baleares"
        mock_catalog = {"tercera_rfef_g11": mock_definition}

        with patch("app.services.top_scorer_service.load_competition_catalog", return_value=mock_catalog):
            candidate = TopScorerService(session).generate("tercera_rfef_g11")

        assert candidate is not None
        assert candidate.content_type == str(ContentType.TOP_SCORER_UPDATE)
        assert candidate.competition_slug == "tercera_rfef_g11"
        assert "GOLEADORES" in candidate.text_draft
        assert "3a RFEF Baleares" in candidate.text_draft
        assert "Nando" in candidate.text_draft
    finally:
        session.close()


def test_generate_text_does_not_exceed_max_characters() -> None:
    session = build_session()
    try:
        _seed_enough_data(session)

        mock_definition = MagicMock()
        mock_definition.editorial_name = "3a RFEF Baleares"
        mock_catalog = {"tercera_rfef_g11": mock_definition}

        with patch("app.services.top_scorer_service.load_competition_catalog", return_value=mock_catalog):
            service = TopScorerService(session, max_characters=240)
            candidate = service.generate("tercera_rfef_g11")

        assert candidate is not None
        assert len(candidate.text_draft) <= 240
    finally:
        session.close()


def test_generate_persists_candidate_as_draft() -> None:
    session = build_session()
    try:
        _seed_enough_data(session)

        mock_definition = MagicMock()
        mock_definition.editorial_name = "3a RFEF Baleares"
        mock_catalog = {"tercera_rfef_g11": mock_definition}

        with patch("app.services.top_scorer_service.load_competition_catalog", return_value=mock_catalog):
            TopScorerService(session).generate("tercera_rfef_g11")
        session.commit()

        rows = session.execute(
            select(ContentCandidate).where(
                ContentCandidate.content_type == str(ContentType.TOP_SCORER_UPDATE),
                ContentCandidate.competition_slug == "tercera_rfef_g11",
            )
        ).scalars().all()

        assert len(rows) == 1
        assert rows[0].status == str(ContentCandidateStatus.DRAFT)
    finally:
        session.close()


def test_generate_payload_contains_scorers_list() -> None:
    session = build_session()
    try:
        _seed_enough_data(session)

        mock_definition = MagicMock()
        mock_definition.editorial_name = "3a RFEF Baleares"
        mock_catalog = {"tercera_rfef_g11": mock_definition}

        with patch("app.services.top_scorer_service.load_competition_catalog", return_value=mock_catalog):
            candidate = TopScorerService(session).generate("tercera_rfef_g11")

        assert candidate is not None
        scorers = candidate.payload_json["source_payload"]["scorers"]
        assert isinstance(scorers, list)
        assert len(scorers) >= 1
        assert all("player" in s and "goals" in s for s in scorers)
        assert scorers[0]["player"] == "Nando"
    finally:
        session.close()


def test_generate_returns_none_when_insufficient_data() -> None:
    session = build_session()
    try:
        competition = _seed_competition(session)
        alpha, beta, _ = _seed_teams(session)

        # Only one covered match — below MIN_TOP_SCORER_SCORER_MATCHES
        m1 = _seed_match(session, competition.id, alpha, beta, external_id="m1-sparse")
        _seed_goal(session, m1, alpha, player="Solitario", sort_order=1, event_key="sparse-1")
        session.commit()

        mock_definition = MagicMock()
        mock_definition.editorial_name = "3a RFEF Baleares"
        mock_catalog = {"tercera_rfef_g11": mock_definition}

        with patch("app.services.top_scorer_service.load_competition_catalog", return_value=mock_catalog):
            candidate = TopScorerService(session).generate("tercera_rfef_g11")

        assert candidate is None
    finally:
        session.close()


def test_generate_dry_run_does_not_persist() -> None:
    session = build_session()
    try:
        _seed_enough_data(session)

        mock_definition = MagicMock()
        mock_definition.editorial_name = "3a RFEF Baleares"
        mock_catalog = {"tercera_rfef_g11": mock_definition}

        with patch("app.services.top_scorer_service.load_competition_catalog", return_value=mock_catalog):
            candidate = TopScorerService(session).generate("tercera_rfef_g11", dry_run=True)
        session.commit()

        assert candidate is not None
        assert "GOLEADORES" in candidate.text_draft

        rows = session.execute(
            select(ContentCandidate).where(
                ContentCandidate.content_type == str(ContentType.TOP_SCORER_UPDATE),
            )
        ).scalars().all()
        assert rows == []
    finally:
        session.close()
