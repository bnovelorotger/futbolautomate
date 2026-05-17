from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class EditorialVoiceUsageConfig(BaseModel):
    apply_only_when_requested: bool = True
    optional: bool = True
    max_local_expressions_per_piece: int = 1


class EditorialVoiceResource(BaseModel):
    id: str
    text: str
    kind: str
    islands: list[str] = Field(default_factory=list)
    registers: list[str] = Field(default_factory=list)
    allowed_content_types: list[str] = Field(default_factory=list)


class EditorialVoiceModeConfig(BaseModel):
    enabled: bool = True
    allowed_content_types: list[str] = Field(default_factory=list)
    resource_ids: list[str] = Field(default_factory=list)


class EditorialVoicePack(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    usage: EditorialVoiceUsageConfig = Field(default_factory=EditorialVoiceUsageConfig)
    blocked_content_types: list[str] = Field(default_factory=list)
    modes: dict[str, EditorialVoiceModeConfig] = Field(default_factory=dict)
    resources: list[EditorialVoiceResource] = Field(default_factory=list)

    def resource_map(self) -> dict[str, EditorialVoiceResource]:
        return {resource.id: resource for resource in self.resources}


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "editorial_voice.json"


@lru_cache(maxsize=1)
def load_editorial_voice_pack(path: Path | None = None) -> EditorialVoicePack:
    config_path = path or _default_config_path()
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return EditorialVoicePack.model_validate(payload)
