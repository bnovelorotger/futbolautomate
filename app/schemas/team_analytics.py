from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class TeamAnalyticsFormWindowView(BaseModel):
    matches_considered: int = 0
    sequence: str = ""
    points: int = 0
    points_per_game: float = 0.0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0


class TeamAnalyticsTrendView(BaseModel):
    direction: str = "stable"
    baseline_points_per_game: float = 0.0
    recent_points_per_game: float = 0.0
    delta_points_per_game: float = 0.0


class TeamAnalyticsVenueSplitView(BaseModel):
    venue: str
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points: int = 0
    points_per_game: float = 0.0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    win_rate_percentage: float = 0.0


class TeamSeasonPaceView(BaseModel):
    current_points: int = 0
    current_points_per_game: float = 0.0
    matches_played: int = 0
    matches_scheduled: int = 0
    matches_remaining: int = 0
    projected_additional_points: float = 0.0
    projected_final_points: float = 0.0


class TeamGoalDifferenceTrendView(BaseModel):
    opening_window_matches: int = 0
    opening_goal_difference_per_match: float = 0.0
    recent_window_matches: int = 0
    recent_goal_difference_per_match: float = 0.0
    delta_goal_difference_per_match: float = 0.0
    direction: str = "stable"


class TeamRecentOutputView(BaseModel):
    matches_considered: int = 0
    total_goals: int = 0
    goals_per_match: float = 0.0


class TeamAnalyticsRowView(BaseModel):
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
    overall_points_per_game: float = 0.0
    last_ten: TeamAnalyticsFormWindowView = Field(default_factory=TeamAnalyticsFormWindowView)
    last_five: TeamAnalyticsFormWindowView = Field(default_factory=TeamAnalyticsFormWindowView)
    recent_trend: TeamAnalyticsTrendView = Field(default_factory=TeamAnalyticsTrendView)
    home_split: TeamAnalyticsVenueSplitView = Field(default_factory=lambda: TeamAnalyticsVenueSplitView(venue="home"))
    away_split: TeamAnalyticsVenueSplitView = Field(default_factory=lambda: TeamAnalyticsVenueSplitView(venue="away"))
    season_pace: TeamSeasonPaceView = Field(default_factory=TeamSeasonPaceView)
    goal_difference_trend: TeamGoalDifferenceTrendView = Field(default_factory=TeamGoalDifferenceTrendView)
    defensive_solidity: TeamRecentOutputView = Field(default_factory=TeamRecentOutputView)
    attacking_efficiency: TeamRecentOutputView = Field(default_factory=TeamRecentOutputView)


class TeamAnalyticsResult(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    generated_at: datetime
    rows: list[TeamAnalyticsRowView] = Field(default_factory=list)
