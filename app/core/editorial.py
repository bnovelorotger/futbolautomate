from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class EditorialRules(BaseModel):
    model_config = ConfigDict(extra="ignore")

    football_terms: list[str] = Field(default_factory=list)
    sport_terms: dict[str, list[str]] = Field(default_factory=dict)
    non_football_penalty_terms: list[str] = Field(default_factory=list)
    balearic_terms: list[str] = Field(default_factory=list)
    target_clubs: dict[str, list[str]] = Field(default_factory=dict)
    target_competitions: dict[str, list[str]] = Field(default_factory=dict)
    score_weights: dict[str, int] = Field(default_factory=dict)
    relevance_threshold: int = 10


@lru_cache(maxsize=1)
def load_editorial_rules() -> EditorialRules:
    path = Path(__file__).resolve().parents[1] / "config" / "editorial_rules.json"
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return EditorialRules.model_validate(payload)
