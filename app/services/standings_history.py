from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.exceptions import ConfigurationError
from app.db.models import Competition, StandingSnapshot, Team
from app.schemas.standings_history import (
    StandingSnapshotRowView,
    StandingsComparisonRowView,
    StandingsComparisonView,
    StandingsSnapshotView,
)


def _normalized_team_key(team_id: int | None, team_name: str) -> str:
    if team_id is not None:
        return f"id:{team_id}"
    return "raw:" + " ".join(team_name.casefold().split())


@dataclass(frozen=True, slots=True)
class SnapshotStandingRow:
    team_key: str
    team: str
    position: int
    points: int | None = None
    played: int | None = None
    wins: int | None = None
    draws: int | None = None
    losses: int | None = None
    goals_for: int | None = None
    goals_against: int | None = None
    goal_difference: int | None = None


@dataclass(frozen=True, slots=True)
class HistoricalStandingsSnapshot:
    competition_slug: str
    competition_name: str
    source_name: str
    snapshot_date: date
    snapshot_timestamp: datetime
    scraper_run_id: int | None
    rows: list[SnapshotStandingRow]


@dataclass(frozen=True, slots=True)
class SnapshotSelector:
    scraper_run_id: int | None
    snapshot_timestamp: datetime


class StandingsHistoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.catalog = load_competition_catalog()

    def latest_snapshot(self, competition_code: str) -> StandingsSnapshotView:
        current_snapshot, _ = self.latest_snapshot_pair(competition_code)
        return self._snapshot_to_view(current_snapshot)

    def compare_latest(self, competition_code: str) -> StandingsComparisonView:
        current_snapshot, previous_snapshot = self.latest_snapshot_pair(competition_code)
        rows: list[StandingsComparisonRowView] = []
        previous_map = (
            {row.team_key: row for row in previous_snapshot.rows}
            if previous_snapshot is not None
            else {}
        )
        for current_row in current_snapshot.rows:
            previous_row = previous_map.get(current_row.team_key)
            previous_position = previous_row.position if previous_row is not None else None
            current_position = current_row.position
            previous_points = previous_row.points if previous_row is not None else None
            current_points = current_row.points
            position_delta = None
            if previous_position is not None:
                position_delta = previous_position - current_position
            points_delta = None
            if previous_points is not None and current_points is not None:
                points_delta = current_points - previous_points
            rows.append(
                StandingsComparisonRowView(
                    team=current_row.team,
                    previous_position=previous_position,
                    current_position=current_position,
                    position_delta=position_delta,
                    previous_points=previous_points,
                    current_points=current_points,
                    points_delta=points_delta,
                )
            )
        return StandingsComparisonView(
            competition_slug=current_snapshot.competition_slug,
            competition_name=current_snapshot.competition_name,
            current_snapshot_timestamp=current_snapshot.snapshot_timestamp,
            previous_snapshot_timestamp=(
                previous_snapshot.snapshot_timestamp if previous_snapshot is not None else None
            ),
            rows=rows,
        )

    def latest_snapshot_pair(
        self,
        competition_code: str,
    ) -> tuple[HistoricalStandingsSnapshot, HistoricalStandingsSnapshot | None]:
        competition = self._competition(competition_code)
        selectors = self._snapshot_selectors(competition.id, limit=2)
        if not selectors:
            raise ConfigurationError(
                f"No hay snapshots historicos de clasificacion para la competicion: {competition_code}"
            )
        current_snapshot = self._load_snapshot(competition, selectors[0])
        previous_snapshot = self._load_snapshot(competition, selectors[1]) if len(selectors) > 1 else None
        return current_snapshot, previous_snapshot

    def _competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(
            select(Competition).where(Competition.code == competition_code)
        )
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_code}")
        return competition

    def _competition_name(self, competition: Competition) -> str:
        definition = self.catalog.get(competition.code)
        if definition is not None and definition.editorial_name:
            return definition.editorial_name
        return competition.name

    def _snapshot_selectors(self, competition_id: int, *, limit: int) -> list[SnapshotSelector]:
        grouped_by_run = self.session.execute(
            select(
                StandingSnapshot.scraper_run_id,
                func.max(StandingSnapshot.snapshot_timestamp).label("snapshot_timestamp"),
            )
            .where(StandingSnapshot.competition_id == competition_id)
            .where(StandingSnapshot.scraper_run_id.is_not(None))
            .group_by(StandingSnapshot.scraper_run_id)
            .order_by(desc(func.max(StandingSnapshot.snapshot_timestamp)))
            .limit(limit)
        ).all()
        if grouped_by_run:
            return [
                SnapshotSelector(
                    scraper_run_id=row.scraper_run_id,
                    snapshot_timestamp=row.snapshot_timestamp,
                )
                for row in grouped_by_run
            ]
        grouped_by_timestamp = self.session.execute(
            select(StandingSnapshot.snapshot_timestamp)
            .where(StandingSnapshot.competition_id == competition_id)
            .group_by(StandingSnapshot.snapshot_timestamp)
            .order_by(desc(StandingSnapshot.snapshot_timestamp))
            .limit(limit)
        ).all()
        return [
            SnapshotSelector(scraper_run_id=None, snapshot_timestamp=row.snapshot_timestamp)
            for row in grouped_by_timestamp
        ]

    def _load_snapshot(
        self,
        competition: Competition,
        selector: SnapshotSelector,
    ) -> HistoricalStandingsSnapshot:
        query = (
            select(
                StandingSnapshot.source_name,
                StandingSnapshot.scraper_run_id,
                StandingSnapshot.snapshot_date,
                StandingSnapshot.snapshot_timestamp,
                StandingSnapshot.position,
                StandingSnapshot.team_id,
                func.coalesce(Team.name, StandingSnapshot.team_raw).label("team"),
                StandingSnapshot.points,
                StandingSnapshot.played,
                StandingSnapshot.wins,
                StandingSnapshot.draws,
                StandingSnapshot.losses,
                StandingSnapshot.goals_for,
                StandingSnapshot.goals_against,
                StandingSnapshot.goal_difference,
            )
            .select_from(StandingSnapshot)
            .outerjoin(Team, Team.id == StandingSnapshot.team_id)
            .where(StandingSnapshot.competition_id == competition.id)
            .order_by(StandingSnapshot.position.asc(), StandingSnapshot.id.asc())
        )
        if selector.scraper_run_id is not None:
            query = query.where(StandingSnapshot.scraper_run_id == selector.scraper_run_id)
        else:
            query = query.where(StandingSnapshot.snapshot_timestamp == selector.snapshot_timestamp)
        rows = self.session.execute(query).all()
        if not rows:
            raise ConfigurationError(
                f"Snapshot historico no disponible para {competition.code} en {selector.snapshot_timestamp}"
            )
        source_name = rows[0].source_name
        snapshot_date = max(row.snapshot_date for row in rows)
        snapshot_timestamp = max(row.snapshot_timestamp for row in rows)
        scraper_run_id = rows[0].scraper_run_id
        items = [
            SnapshotStandingRow(
                team_key=_normalized_team_key(row.team_id, row.team),
                team=row.team,
                position=row.position,
                points=row.points,
                played=row.played,
                wins=row.wins,
                draws=row.draws,
                losses=row.losses,
                goals_for=row.goals_for,
                goals_against=row.goals_against,
                goal_difference=row.goal_difference,
            )
            for row in rows
        ]
        return HistoricalStandingsSnapshot(
            competition_slug=competition.code,
            competition_name=self._competition_name(competition),
            source_name=source_name,
            snapshot_date=snapshot_date,
            snapshot_timestamp=snapshot_timestamp,
            scraper_run_id=scraper_run_id,
            rows=items,
        )

    def _snapshot_to_view(self, snapshot: HistoricalStandingsSnapshot) -> StandingsSnapshotView:
        return StandingsSnapshotView(
            competition_slug=snapshot.competition_slug,
            competition_name=snapshot.competition_name,
            source_name=snapshot.source_name,
            snapshot_date=snapshot.snapshot_date,
            snapshot_timestamp=snapshot.snapshot_timestamp,
            rows=[
                StandingSnapshotRowView(
                    position=row.position,
                    team=row.team,
                    points=row.points,
                    played=row.played,
                    wins=row.wins,
                    draws=row.draws,
                    losses=row.losses,
                    goals_for=row.goals_for,
                    goals_against=row.goals_against,
                    goal_difference=row.goal_difference,
                )
                for row in snapshot.rows
            ],
        )
