from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class StandingSnapshotRowView(BaseModel):
    position: int
    team: str
    points: int | None = None
    played: int | None = None
    wins: int | None = None
    draws: int | None = None
    losses: int | None = None
    goals_for: int | None = None
    goals_against: int | None = None
    goal_difference: int | None = None


class StandingsSnapshotView(BaseModel):
    competition_slug: str
    competition_name: str
    source_name: str
    snapshot_date: date
    snapshot_timestamp: datetime
    rows: list[StandingSnapshotRowView] = Field(default_factory=list)


class StandingsComparisonRowView(BaseModel):
    team: str
    previous_position: int | None = None
    current_position: int | None = None
    position_delta: int | None = None
    previous_points: int | None = None
    current_points: int | None = None
    points_delta: int | None = None


class StandingsComparisonView(BaseModel):
    competition_slug: str
    competition_name: str
    current_snapshot_timestamp: datetime
    previous_snapshot_timestamp: datetime | None = None
    rows: list[StandingsComparisonRowView] = Field(default_factory=list)
