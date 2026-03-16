from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import ContentType, FormEventType
from app.schemas.common import IngestStats


class TeamFormEntryView(BaseModel):
    rank: int
    team: str
    matches_considered: int
    sequence: str
    points: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    current_win_streak: int
    current_loss_streak: int
    longest_win_streak: int
    longest_loss_streak: int


class TeamFormEventView(BaseModel):
    competition_slug: str
    competition_name: str
    content_type: ContentType = ContentType.FORM_EVENT
    event_type: FormEventType
    priority: int
    title: str
    team: str
    sequence: str
    matches_considered: int
    points: int
    metric_value: int
    excerpt: str
    text_draft: str
    source_summary_hash: str


class TeamFormResult(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    window_size: int
    generated_at: datetime
    rows: list[TeamFormEntryView] = Field(default_factory=list)
    events: list[TeamFormEventView] = Field(default_factory=list)


class TeamFormGenerationResult(TeamFormResult):
    stats: IngestStats = Field(default_factory=IngestStats)
