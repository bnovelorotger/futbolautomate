from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


class CompetitionStandingsZones(BaseModel):
    playoff_positions: list[int] = Field(default_factory=list)
    relegation_positions: list[int] = Field(default_factory=list)


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "standings_zones.json"


@lru_cache(maxsize=1)
def load_standings_zones(path: Path | None = None) -> dict[str, CompetitionStandingsZones]:
    config_path = path or _default_config_path()
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return {
        competition_slug: CompetitionStandingsZones.model_validate(config)
        for competition_slug, config in payload.items()
    }
