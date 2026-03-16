from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.reporting import CompetitionMatchView, StandingView, TeamRankingView


class EditorialSummaryMetadata(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    generated_at: datetime


class EditorialCompetitionState(BaseModel):
    total_teams: int
    total_matches: int
    played_matches: int
    pending_matches: int


class EditorialRankings(BaseModel):
    best_attack: TeamRankingView | None = None
    best_defense: TeamRankingView | None = None
    most_wins: TeamRankingView | None = None


class EditorialCalendarWindows(BaseModel):
    today: list[CompetitionMatchView]
    tomorrow: list[CompetitionMatchView]
    next_weekend: list[CompetitionMatchView]


class EditorialSummaryNewsItem(BaseModel):
    source_name: str
    source_url: str
    title: str
    published_at: datetime | None = None
    summary: str | None = None
    clubs_detected: list[str] | None = None
    competition_detected: str | None = None
    editorial_relevance_score: int
    selection_reason: str


class EditorialAggregateMetrics(BaseModel):
    total_goals_scored: int
    average_goals_per_played_match: float | None = None
    relevant_news_count: int


class CompetitionEditorialSummary(BaseModel):
    metadata: EditorialSummaryMetadata
    competition_state: EditorialCompetitionState
    latest_results: list[CompetitionMatchView]
    upcoming_matches: list[CompetitionMatchView]
    current_standings: list[StandingView]
    rankings: EditorialRankings
    calendar_windows: EditorialCalendarWindows
    editorial_news: list[EditorialSummaryNewsItem]
    aggregate_metrics: EditorialAggregateMetrics
