from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel

from app.core.enums import MatchWindow


class CompetitionMatchView(BaseModel):
    round_name: str | None = None
    match_date: date | None = None
    match_date_raw: str | None = None
    match_time: time | None = None
    match_time_raw: str | None = None
    kickoff_datetime: datetime | None = None
    home_team: str
    away_team: str
    home_score: int | None = None
    away_score: int | None = None
    status: str
    source_url: str


class StandingView(BaseModel):
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


class TeamRankingView(BaseModel):
    team: str
    value: int | None = None
    position: int | None = None


class CompetitionSummaryView(BaseModel):
    competition_code: str
    competition_name: str
    total_teams: int
    total_matches: int
    played_matches: int
    pending_matches: int


class MatchWindowView(BaseModel):
    window: MatchWindow
    start_date: date
    end_date: date
    matches: list[CompetitionMatchView]


class NewsView(BaseModel):
    source_name: str
    source_url: str
    title: str
    published_at: datetime | None = None
    summary: str | None = None
    raw_category: str | None = None
    news_type: str
    scraped_at: datetime


class EditorialNewsView(BaseModel):
    news_id: int
    source_name: str
    source_url: str
    title: str
    published_at: datetime | None = None
    summary: str | None = None
    raw_category: str | None = None
    sport_detected: str | None = None
    is_football: bool
    is_balearic_related: bool
    clubs_detected: list[str] | None = None
    competition_detected: str | None = None
    editorial_relevance_score: int


class EditorialSummaryView(BaseModel):
    relevant_balearic_football: int
    football_non_balearic: int
    other_sports_or_unknown: int
