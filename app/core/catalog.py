from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    CompetitionIntegrationStatus,
    CompetitionReferenceRole,
    Gender,
    SourceName,
    TargetType,
)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class SourceDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: SourceName
    base_url: str
    supports: list[TargetType]
    requires_playwright: bool = False
    rate_limit_seconds: float = 1.0
    headers: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None


class CompetitionSourceMapping(BaseModel):
    model_config = ConfigDict(extra="ignore")

    competition_id: str | None = None
    urls: dict[TargetType, str] = Field(default_factory=dict)
    enabled: bool = True
    notes: str | None = None


class CompetitionReference(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_name: str
    role: CompetitionReferenceRole
    urls: list[str] = Field(default_factory=list)
    notes: str | None = None


class CompetitionDefinition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    name: str
    editorial_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    historical_backlog_names: list[str] = Field(default_factory=list)
    category_level: int | None = None
    gender: Gender = Gender.UNKNOWN
    region: str | None = None
    country: str = "Spain"
    federation: str | None = None
    priority: int = 99
    status: CompetitionIntegrationStatus = CompetitionIntegrationStatus.DEFERRED
    primary_source: str | None = None
    coverage_scope: str | None = None
    integration_notes: str | None = None
    group_name: str | None = None
    season: str | None = None
    tracked_teams: list[str] = Field(default_factory=list)
    references: list[CompetitionReference] = Field(default_factory=list)
    sources: dict[SourceName, CompetitionSourceMapping] = Field(default_factory=dict)


class TeamAliasCatalog(BaseModel):
    aliases: dict[str, str] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def load_source_catalog() -> dict[SourceName, SourceDefinition]:
    path = Path(__file__).resolve().parents[1] / "config" / "sources.json"
    return {
        SourceName(entry["name"]): SourceDefinition.model_validate(entry)
        for entry in _load_json(path)
    }


@lru_cache(maxsize=1)
def load_competition_catalog() -> dict[str, CompetitionDefinition]:
    path = Path(__file__).resolve().parents[1] / "config" / "competitions.json"
    entries = _load_json(path)
    return {entry["code"]: CompetitionDefinition.model_validate(entry) for entry in entries}


@lru_cache(maxsize=1)
def load_team_alias_catalog() -> TeamAliasCatalog:
    path = Path(__file__).resolve().parents[1] / "config" / "team_aliases.json"
    return TeamAliasCatalog.model_validate(_load_json(path))
