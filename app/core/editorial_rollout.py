from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ContentType, ViralStoryType


class Phase3PreviewRolloutConfig(BaseModel):
    enabled: bool = True
    min_priority: int = 90
    require_featured_match: bool = True
    editorial_voice_mode: str = "preview_light"
    editorial_voice_resource_id: str = "quin_partidas"


class Phase3ViralStoryRolloutConfig(BaseModel):
    enabled: bool = True
    min_priority: int = 69
    allowed_story_types: list[str] = Field(default_factory=list)
    editorial_voice_mode: str = "viral_story_light"
    resource_by_story_type: dict[str, str] = Field(default_factory=dict)


class Phase3RolloutConfig(BaseModel):
    allowed_content_types: list[str] = Field(default_factory=lambda: ["preview", "viral_story"])
    allowed_competitions: list[str] = Field(default_factory=list)
    preview: Phase3PreviewRolloutConfig = Field(default_factory=Phase3PreviewRolloutConfig)
    viral_story: Phase3ViralStoryRolloutConfig = Field(default_factory=Phase3ViralStoryRolloutConfig)


class EditorialRolloutConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    phase3: Phase3RolloutConfig = Field(default_factory=Phase3RolloutConfig)


class EditorialPhase3Decision(BaseModel):
    eligible: bool
    reason: str
    content_type: str
    editorial_voice_request: dict[str, Any] | None = None


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "editorial_rollout.json"


@lru_cache(maxsize=1)
def load_editorial_rollout_config(path: Path | None = None) -> EditorialRolloutConfig:
    config_path = path or _default_config_path()
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return EditorialRolloutConfig.model_validate(payload)


def evaluate_phase3_rollout(
    content_type: ContentType,
    *,
    priority: int,
    competition_slug: str | None,
    payload_json: dict[str, Any] | None,
    humanized_local_enabled: bool,
    phase3_rollout_enabled: bool,
) -> EditorialPhase3Decision:
    content_type_value = str(content_type)
    if not humanized_local_enabled:
        return EditorialPhase3Decision(
            eligible=False,
            reason="humanized_local_disabled",
            content_type=content_type_value,
        )
    if not phase3_rollout_enabled:
        return EditorialPhase3Decision(
            eligible=False,
            reason="phase3_rollout_disabled",
            content_type=content_type_value,
        )

    config = load_editorial_rollout_config().phase3
    if content_type_value not in config.allowed_content_types:
        return EditorialPhase3Decision(
            eligible=False,
            reason="content_type_not_in_phase3",
            content_type=content_type_value,
        )
    if config.allowed_competitions and competition_slug not in config.allowed_competitions:
        return EditorialPhase3Decision(
            eligible=False,
            reason="competition_not_allowlisted",
            content_type=content_type_value,
        )

    source_payload = {}
    if isinstance(payload_json, dict) and isinstance(payload_json.get("source_payload"), dict):
        source_payload = payload_json["source_payload"]

    if content_type == ContentType.PREVIEW:
        return _preview_phase3_decision(
            priority=priority,
            source_payload=source_payload,
            config=config.preview,
        )
    if content_type == ContentType.VIRAL_STORY:
        return _viral_story_phase3_decision(
            priority=priority,
            source_payload=source_payload,
            config=config.viral_story,
        )
    return EditorialPhase3Decision(
        eligible=False,
        reason="content_type_not_supported",
        content_type=content_type_value,
    )


def with_phase3_editorial_voice(
    payload_json: dict[str, Any] | None,
    content_type: ContentType,
    *,
    priority: int,
    competition_slug: str | None,
    humanized_local_enabled: bool,
    phase3_rollout_enabled: bool,
) -> tuple[dict[str, Any], EditorialPhase3Decision]:
    normalized_payload = dict(payload_json or {})
    existing_request = normalized_payload.get("editorial_voice")
    if isinstance(existing_request, dict):
        return normalized_payload, EditorialPhase3Decision(
            eligible=True,
            reason="editorial_voice_preexisting",
            content_type=str(content_type),
            editorial_voice_request=existing_request,
        )

    decision = evaluate_phase3_rollout(
        content_type,
        priority=priority,
        competition_slug=competition_slug,
        payload_json=normalized_payload,
        humanized_local_enabled=humanized_local_enabled,
        phase3_rollout_enabled=phase3_rollout_enabled,
    )
    if decision.editorial_voice_request is not None:
        normalized_payload["editorial_voice"] = decision.editorial_voice_request
    return normalized_payload, decision


def _preview_phase3_decision(
    *,
    priority: int,
    source_payload: dict[str, Any],
    config: Phase3PreviewRolloutConfig,
) -> EditorialPhase3Decision:
    if not config.enabled:
        return EditorialPhase3Decision(
            eligible=False,
            reason="preview_rollout_disabled",
            content_type=str(ContentType.PREVIEW),
        )
    if priority < config.min_priority:
        return EditorialPhase3Decision(
            eligible=False,
            reason=f"preview_priority_below_min:{config.min_priority}",
            content_type=str(ContentType.PREVIEW),
        )
    if config.require_featured_match and not isinstance(source_payload.get("featured_match"), dict):
        return EditorialPhase3Decision(
            eligible=False,
            reason="preview_missing_featured_match",
            content_type=str(ContentType.PREVIEW),
        )
    return EditorialPhase3Decision(
        eligible=True,
        reason="phase3_preview_eligible",
        content_type=str(ContentType.PREVIEW),
        editorial_voice_request={
            "mode": config.editorial_voice_mode,
            "resource_id": config.editorial_voice_resource_id,
        },
    )


def _viral_story_phase3_decision(
    *,
    priority: int,
    source_payload: dict[str, Any],
    config: Phase3ViralStoryRolloutConfig,
) -> EditorialPhase3Decision:
    if not config.enabled:
        return EditorialPhase3Decision(
            eligible=False,
            reason="viral_story_rollout_disabled",
            content_type=str(ContentType.VIRAL_STORY),
        )
    if priority < config.min_priority:
        return EditorialPhase3Decision(
            eligible=False,
            reason=f"viral_story_priority_below_min:{config.min_priority}",
            content_type=str(ContentType.VIRAL_STORY),
        )

    story_type = _viral_story_type(source_payload.get("story_type"))
    if story_type is None:
        return EditorialPhase3Decision(
            eligible=False,
            reason="viral_story_type_missing",
            content_type=str(ContentType.VIRAL_STORY),
        )
    story_type_value = str(story_type)
    if story_type_value not in config.allowed_story_types:
        return EditorialPhase3Decision(
            eligible=False,
            reason=f"viral_story_type_not_allowlisted:{story_type_value}",
            content_type=str(ContentType.VIRAL_STORY),
        )

    resource_id = config.resource_by_story_type.get(story_type_value)
    if not resource_id:
        return EditorialPhase3Decision(
            eligible=False,
            reason=f"viral_story_resource_missing:{story_type_value}",
            content_type=str(ContentType.VIRAL_STORY),
        )
    return EditorialPhase3Decision(
        eligible=True,
        reason=f"phase3_viral_story_eligible:{story_type_value}",
        content_type=str(ContentType.VIRAL_STORY),
        editorial_voice_request={
            "mode": config.editorial_voice_mode,
            "resource_id": resource_id,
        },
    )


def _viral_story_type(value: Any) -> ViralStoryType | None:
    if isinstance(value, ViralStoryType):
        return value
    if isinstance(value, str):
        try:
            return ViralStoryType(value)
        except ValueError:
            return None
    return None
