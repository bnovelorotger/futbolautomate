from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select

from app.core.enums import StandingsEventType
from app.core.standings_zones import CompetitionStandingsZones
from app.db.models import Competition, StandingSnapshot, Team
from app.services.standings_events import StandingsEventsService
from app.services.standings_history import StandingsHistoryService
from tests.unit.services.test_editorial_narratives import build_session, seed_competition


def seed_standings_snapshots(
    session,
    *,
    competition_code: str,
    competition_name: str,
    snapshots: list[dict],
) -> None:
    teams = sorted(
        {
            row["team"]
            for snapshot in snapshots
            for row in snapshot["rows"]
        }
    )
    seed_competition(
        session,
        code=competition_code,
        name=competition_name,
        teams=teams,
        standings_rows=snapshots[-1]["rows"],
        match_rows=[],
    )
    competition = session.scalar(select(Competition).where(Competition.code == competition_code))
    assert competition is not None
    team_rows = session.execute(select(Team).where(Team.name.in_(teams))).scalars().all()
    team_map = {team.name: team for team in team_rows}
    for index, snapshot in enumerate(snapshots, start=1):
        timestamp = snapshot["timestamp"]
        for row_index, row in enumerate(snapshot["rows"], start=1):
            team = team_map[row["team"]]
            session.add(
                StandingSnapshot(
                    source_name="futbolme",
                    source_url=f"https://example.com/{competition_code}/standings",
                    competition_id=competition.id,
                    scraper_run_id=index,
                    season="2025-26",
                    group_name="Grupo test",
                    snapshot_date=timestamp.date(),
                    snapshot_timestamp=timestamp,
                    position=row["position"],
                    team_id=team.id,
                    team_raw=row["team"],
                    played=row.get("played"),
                    wins=row.get("wins"),
                    draws=row.get("draws"),
                    losses=row.get("losses"),
                    goals_for=row.get("goals_for"),
                    goals_against=row.get("goals_against"),
                    goal_difference=row.get("goal_difference"),
                    points=row.get("points"),
                    form_text=None,
                    scraped_at=timestamp,
                    content_hash=f"{competition_code}-{index}-{row_index}",
                    extra_data=None,
                )
            )
    session.commit()


def _table_rows(order: list[str]) -> list[dict]:
    base_points = 60
    rows: list[dict] = []
    for index, team in enumerate(order, start=1):
        rows.append(
            {
                "position": index,
                "team": team,
                "played": 28,
                "wins": max(0, 18 - index),
                "draws": index % 4,
                "losses": index % 3,
                "goals_for": max(10, base_points - index * 2),
                "goals_against": 15 + index,
                "goal_difference": max(10, base_points - index * 2) - (15 + index),
                "points": base_points - index * 2,
            }
        )
    return rows


def test_standings_history_compares_latest_snapshots() -> None:
    session = build_session()
    try:
        seed_standings_snapshots(
            session,
            competition_code="tercera_rfef_g11",
            competition_name="3a RFEF Grupo 11",
            snapshots=[
                {
                    "timestamp": datetime(2026, 3, 9, 8, 0, tzinfo=timezone.utc),
                    "rows": _table_rows(["CE Alpha", "CE Beta", "CE Gamma", "CE Delta"]),
                },
                {
                    "timestamp": datetime(2026, 3, 16, 8, 0, tzinfo=timezone.utc),
                    "rows": _table_rows(["CE Beta", "CE Alpha", "CE Gamma", "CE Delta"]),
                },
            ],
        )

        result = StandingsHistoryService(session).compare_latest("tercera_rfef_g11")

        assert result.previous_snapshot_timestamp is not None
        beta_row = next(row for row in result.rows if row.team == "CE Beta")
        alpha_row = next(row for row in result.rows if row.team == "CE Alpha")
        assert beta_row.previous_position == 2
        assert beta_row.current_position == 1
        assert beta_row.position_delta == 1
        assert alpha_row.previous_position == 1
        assert alpha_row.current_position == 2
        assert alpha_row.position_delta == -1
    finally:
        session.close()


def test_standings_events_detect_key_table_events_with_configured_zones() -> None:
    session = build_session()
    try:
        seed_standings_snapshots(
            session,
            competition_code="tercera_rfef_g11",
            competition_name="3a RFEF Grupo 11",
            snapshots=[
                {
                    "timestamp": datetime(2026, 3, 9, 8, 0, tzinfo=timezone.utc),
                    "rows": _table_rows(
                        [
                            "CE Alpha",
                            "CE Beta",
                            "CE Gamma",
                            "CE Delta",
                            "CE Epsilon",
                            "CE Foxtrot",
                            "CE Gama",
                            "CE Hotel",
                        ]
                    ),
                },
                {
                    "timestamp": datetime(2026, 3, 16, 8, 0, tzinfo=timezone.utc),
                    "rows": _table_rows(
                        [
                            "CE Beta",
                            "CE Gamma",
                            "CE Gama",
                            "CE Alpha",
                            "CE Epsilon",
                            "CE Delta",
                            "CE Foxtrot",
                            "CE Hotel",
                        ]
                    ),
                },
            ],
        )
        service = StandingsEventsService(
            session,
            zones={
                "tercera_rfef_g11": CompetitionStandingsZones(
                    playoff_positions=[1, 2, 3, 4],
                    relegation_positions=[7, 8],
                )
            },
        )

        result = service.preview_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 16))

        event_types = {(row.event_type, row.team) for row in result.rows}
        assert (StandingsEventType.NEW_LEADER, "CE Beta") in event_types
        assert (StandingsEventType.ENTERED_PLAYOFF, "CE Gama") in event_types
        assert (StandingsEventType.LEFT_PLAYOFF, "CE Delta") in event_types
        assert (StandingsEventType.ENTERED_RELEGATION, "CE Foxtrot") in event_types
        assert (StandingsEventType.LEFT_RELEGATION, "CE Gama") in event_types
        assert (StandingsEventType.BIGGEST_POSITION_RISE, "CE Gama") in event_types
        assert (StandingsEventType.BIGGEST_POSITION_DROP, "CE Alpha") in event_types
    finally:
        session.close()


def test_standings_events_do_not_treat_leader_transition_as_playoff_entry_or_exit() -> None:
    session = build_session()
    try:
        seed_standings_snapshots(
            session,
            competition_code="tercera_rfef_g11",
            competition_name="3a RFEF Grupo 11",
            snapshots=[
                {
                    "timestamp": datetime(2026, 3, 9, 8, 0, tzinfo=timezone.utc),
                    "rows": _table_rows(
                        [
                            "CE Alpha",
                            "CE Beta",
                            "CE Gamma",
                            "CE Delta",
                            "CE Epsilon",
                            "CE Foxtrot",
                        ]
                    ),
                },
                {
                    "timestamp": datetime(2026, 3, 16, 8, 0, tzinfo=timezone.utc),
                    "rows": _table_rows(
                        [
                            "CE Beta",
                            "CE Gamma",
                            "CE Delta",
                            "CE Alpha",
                            "CE Epsilon",
                            "CE Foxtrot",
                        ]
                    ),
                },
            ],
        )
        service = StandingsEventsService(
            session,
            zones={
                "tercera_rfef_g11": CompetitionStandingsZones(
                    playoff_positions=[2, 3, 4, 5],
                    relegation_positions=[],
                )
            },
        )

        result = service.preview_for_competition("tercera_rfef_g11", reference_date=date(2026, 3, 16))

        leader_boundary_events = {
            (row.event_type, row.team)
            for row in result.rows
            if row.team in {"CE Alpha", "CE Beta"}
            and row.event_type in {
                StandingsEventType.ENTERED_PLAYOFF,
                StandingsEventType.LEFT_PLAYOFF,
            }
        }
        assert leader_boundary_events == set()
    finally:
        session.close()
