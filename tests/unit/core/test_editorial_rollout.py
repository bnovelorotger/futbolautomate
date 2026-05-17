from __future__ import annotations

from app.core.editorial_rollout import evaluate_phase3_rollout
from app.core.enums import ContentType


def test_phase3_rollout_allows_preview_with_featured_match_and_priority() -> None:
    decision = evaluate_phase3_rollout(
        ContentType.PREVIEW,
        priority=90,
        competition_slug="segunda_rfef_g3_baleares",
        payload_json={
            "source_payload": {
                "featured_match": {
                    "round_name": "Jornada 28",
                    "home_team": "Atletico Baleares",
                    "away_team": "UD Poblense",
                }
            }
        },
        humanized_local_enabled=True,
        phase3_rollout_enabled=True,
    )

    assert decision.eligible is True
    assert decision.reason == "phase3_preview_eligible"
    assert decision.editorial_voice_request == {
        "mode": "preview_light",
        "resource_id": "quin_partidas",
    }


def test_phase3_rollout_blocks_preview_when_global_phase3_flag_is_off() -> None:
    decision = evaluate_phase3_rollout(
        ContentType.PREVIEW,
        priority=90,
        competition_slug="segunda_rfef_g3_baleares",
        payload_json={"source_payload": {"featured_match": {"home_team": "A", "away_team": "B"}}},
        humanized_local_enabled=True,
        phase3_rollout_enabled=False,
    )

    assert decision.eligible is False
    assert decision.reason == "phase3_rollout_disabled"


def test_phase3_rollout_allows_supported_positive_viral_story() -> None:
    decision = evaluate_phase3_rollout(
        ContentType.VIRAL_STORY,
        priority=76,
        competition_slug="tercera_rfef_g11",
        payload_json={"source_payload": {"story_type": "win_streak"}},
        humanized_local_enabled=True,
        phase3_rollout_enabled=True,
    )

    assert decision.eligible is True
    assert decision.reason == "phase3_viral_story_eligible:win_streak"
    assert decision.editorial_voice_request == {
        "mode": "viral_story_light",
        "resource_id": "molt_bona_feina",
    }


def test_phase3_rollout_blocks_non_allowlisted_viral_story() -> None:
    decision = evaluate_phase3_rollout(
        ContentType.VIRAL_STORY,
        priority=74,
        competition_slug="tercera_rfef_g11",
        payload_json={"source_payload": {"story_type": "losing_streak"}},
        humanized_local_enabled=True,
        phase3_rollout_enabled=True,
    )

    assert decision.eligible is False
    assert decision.reason == "viral_story_type_not_allowlisted:losing_streak"
