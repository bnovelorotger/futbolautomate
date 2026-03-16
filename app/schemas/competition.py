from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.core.enums import Gender


class CompetitionSeed(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    name: str
    normalized_name: str
    category_level: int | None = None
    gender: Gender = Gender.UNKNOWN
    region: str | None = None
    country: str = "Spain"
    federation: str | None = None
    source_name: str | None = None
    source_competition_id: str | None = None

