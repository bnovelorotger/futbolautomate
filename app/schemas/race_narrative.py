from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RaceNarrativeType(StrEnum):
    TITLE_RACE = "title_race"
    PLAYOFF_RACE = "playoff_race"
    RELEGATION_RACE = "relegation_race"
    ALIVE_MATHEMATICS = "alive_mathematics"


class RaceNarrativeConfig(BaseModel):
    min_title_teams: int = 2
    min_playoff_teams: int = 3
    min_relegation_teams: int = 3
    title_max_gap_points: int = 2
    playoff_max_gap_points: int = 2
    relegation_max_gap_points: int = 2
    alive_math_min_teams: int = 3
    alive_math_max_teams: int | None = 6
    alive_math_min_rounds_remaining: int = 2
    alive_math_max_rounds_remaining: int | None = 8


class RaceNarrativeSeasonContext(BaseModel):
    total_matchdays: int | None = None
    rounds_remaining: int | None = None


class RaceNarrativeTeamSnapshot(BaseModel):
    team: str
    position: int
    points: int
    goal_difference: int | None = None
    played: int | None = None
    matches_remaining: int | None = None
    max_points: int | None = None
    gap_to_target: int | None = None


class RaceNarrativeCandidateView(BaseModel):
    competition_slug: str
    competition_name: str
    narrative_type: RaceNarrativeType
    title: str
    priority: int
    intensity_score: int
    teams: list[RaceNarrativeTeamSnapshot] = Field(default_factory=list)
    team_count: int
    points_span: int
    target_position: int | None = None
    target_label: str
    rounds_remaining: int | None = None
    excerpt: str
    text_draft: str
    content_key: str
    template_name: str
    source_payload: dict[str, Any] = Field(default_factory=dict)
    source_summary_hash: str


class RaceNarrativeResult(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    generated_at: datetime
    rows: list[RaceNarrativeCandidateView] = Field(default_factory=list)
