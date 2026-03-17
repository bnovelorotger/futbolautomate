from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import ContentCandidateStatus, ContentType


class StoryImportanceCandidateView(BaseModel):
    candidate_id: int
    competition_slug: str
    content_type: ContentType
    status: ContentCandidateStatus
    current_priority: int
    importance_score: int
    importance_reasoning: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    priority_bucket: str
    excerpt: str
    created_at: datetime | None = None
    published_at: datetime | None = None


class StoryImportanceListResult(BaseModel):
    reference_date: date | None = None
    generated_at: datetime
    rows: list[StoryImportanceCandidateView] = Field(default_factory=list)


class StoryImportanceScoreResult(BaseModel):
    generated_at: datetime
    candidate: StoryImportanceCandidateView


class StoryImportanceAutomationDecision(BaseModel):
    candidate_id: int
    competition_slug: str
    content_type: ContentType
    importance_score: int
    priority_bucket: str
    importance_reasoning: list[str] = Field(default_factory=list)
    team_keys: list[str] = Field(default_factory=list)
    allowed: bool
    reason: str
