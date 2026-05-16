from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import StrEnum


class MatchImpactScenario(StrEnum):
    HOME_WIN = "home_win"
    DRAW = "draw"
    AWAY_WIN = "away_win"


class MatchImpactTableRowView(BaseModel):
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
    zone_tags: list[str] = Field(default_factory=list)


class MatchImpactTeamStateView(BaseModel):
    team: str
    current_position: int | None = None
    current_points: int | None = None
    current_zone_tags: list[str] = Field(default_factory=list)
    projected_position: int | None = None
    projected_points: int | None = None
    projected_zone_tags: list[str] = Field(default_factory=list)
    position_delta: int | None = None
    points_delta: int | None = None


class MatchImpactZoneCrossingView(BaseModel):
    team: str
    event_type: str
    zone: str
    previous_position: int | None = None
    projected_position: int | None = None
    previous_zone_tags: list[str] = Field(default_factory=list)
    projected_zone_tags: list[str] = Field(default_factory=list)


class MatchImpactOutcomeView(BaseModel):
    scenario: MatchImpactScenario
    label: str
    crossing_count: int
    impacted_zones: list[str] = Field(default_factory=list)
    zone_crossings: list[MatchImpactZoneCrossingView] = Field(default_factory=list)
    home_team: MatchImpactTeamStateView
    away_team: MatchImpactTeamStateView
    projected_table: list[MatchImpactTableRowView] = Field(default_factory=list)


class MatchImpactMatchView(BaseModel):
    competition_slug: str
    competition_name: str
    round_name: str | None = None
    match_date: date | None = None
    source_url: str
    home_team: str
    away_team: str
    home_team_state: MatchImpactTeamStateView
    away_team_state: MatchImpactTeamStateView
    max_zone_crossings: int
    total_zone_crossings: int
    impact_score: int
    scenarios: list[MatchImpactOutcomeView] = Field(default_factory=list)


class MatchImpactResult(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    generated_at: datetime
    rows: list[MatchImpactMatchView] = Field(default_factory=list)


class MatchImpactCandidatePayload(BaseModel):
    competition_slug: str
    content_type: str = "match_impact_scenario"
    round_name: str | None = None
    match_date: date | None = None
    source_url: str
    home_team: str
    away_team: str
    home_team_state: MatchImpactTeamStateView
    away_team_state: MatchImpactTeamStateView
    max_zone_crossings: int
    total_zone_crossings: int
    impact_score: int
    scenarios: list[MatchImpactOutcomeView] = Field(default_factory=list)
