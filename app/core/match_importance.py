from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


class MatchImportanceWeights(BaseModel):
    title_race: int = 28
    top_table_match: int = 18
    playoff_clash: int = 18
    relegation_clash: int = 18
    direct_rivalry: int = 14
    hot_form_match: int = 14
    cold_form_match: int = 8


class MatchImportanceConfig(BaseModel):
    top_zone_positions: list[int] = Field(default_factory=list)
    playoff_positions: list[int] = Field(default_factory=list)
    bottom_zone_positions: list[int] = Field(default_factory=list)
    direct_rival_gap_max: int = 3
    near_playoff_margin: int = 1
    near_bottom_margin: int = 1
    hot_form_points_threshold: int = 10
    cold_form_points_threshold: int = 4
    weights: MatchImportanceWeights = Field(default_factory=MatchImportanceWeights)


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "match_importance.json"


@lru_cache(maxsize=1)
def load_match_importance_config(
    path: Path | None = None,
) -> dict[str, MatchImportanceConfig]:
    config_path = path or _default_config_path()
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return {
        competition_slug: MatchImportanceConfig.model_validate(config)
        for competition_slug, config in payload.items()
    }
