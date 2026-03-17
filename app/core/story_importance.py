from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


class StoryImportanceBucketConfig(BaseModel):
    critical: int = 110
    high: int = 80
    medium: int = 50


class StoryImportanceTableContextConfig(BaseModel):
    leader: int = 18
    playoff: int = 12
    relegation: int = 12


class StoryImportanceTeamFormConfig(BaseModel):
    strong_recent_points_threshold: int = 10
    strong_recent_points_bonus: int = 6
    elite_recent_points_threshold: int = 13
    elite_recent_points_bonus: int = 10
    streak_3_plus_bonus: int = 4
    streak_5_plus_bonus: int = 8


class StoryImportanceRepetitionConfig(BaseModel):
    window_hours: int = 72
    same_content_key_penalty: int = 45
    same_kind_penalty: int = 20
    same_team_penalty: int = 12
    same_content_type_penalty: int = 8


class StoryImportanceIntensityConfig(BaseModel):
    standings_event_weights: dict[str, int] = Field(default_factory=dict)
    viral_story_base_weights: dict[str, int] = Field(default_factory=dict)
    viral_story_per_unit_weights: dict[str, float] = Field(default_factory=dict)
    form_event_weights: dict[str, int] = Field(default_factory=dict)
    featured_match_importance_multiplier: float = 0.45
    featured_match_tag_weights: dict[str, int] = Field(default_factory=dict)
    results_roundup_per_match: int = 3
    results_roundup_complete_bonus: int = 6
    results_roundup_omitted_penalty: int = 2
    results_roundup_max_match_bonus: int = 24


class StoryImportanceConfig(BaseModel):
    content_type_weights: dict[str, int] = Field(default_factory=dict)
    competition_weights: dict[str, float] = Field(default_factory=dict)
    intensity: StoryImportanceIntensityConfig = Field(default_factory=StoryImportanceIntensityConfig)
    table_context: StoryImportanceTableContextConfig = Field(default_factory=StoryImportanceTableContextConfig)
    team_form: StoryImportanceTeamFormConfig = Field(default_factory=StoryImportanceTeamFormConfig)
    repetition: StoryImportanceRepetitionConfig = Field(default_factory=StoryImportanceRepetitionConfig)
    buckets: StoryImportanceBucketConfig = Field(default_factory=StoryImportanceBucketConfig)


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "story_importance.json"


@lru_cache(maxsize=1)
def load_story_importance_config(path: Path | None = None) -> StoryImportanceConfig:
    config_path = path or _default_config_path()
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return StoryImportanceConfig.model_validate(payload)
