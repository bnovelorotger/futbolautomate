from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import Competition, ContentCandidate
from app.services.story_importance import StoryImportanceService
from tests.unit.services.service_test_support import build_session, build_settings


def seed_competition(session) -> None:
    session.add(
        Competition(
            code="tercera_rfef_g11",
            name="3a RFEF Grupo 11",
            normalized_name="3a rfef grupo 11",
            category_level=5,
            gender="male",
            region="Baleares",
            country="Spain",
            federation="RFEF",
            source_name="futbolme",
            source_competition_id="3065",
        )
    )
    session.commit()


def add_candidate(
    session,
    *,
    candidate_id: int,
    content_type: str,
    priority: int,
    text_draft: str,
    payload_json: dict,
    status: str = "published",
    published: bool = True,
    external_ref: str | None = None,
) -> None:
    timestamp = datetime(2026, 3, 17, 10, candidate_id % 50, tzinfo=timezone.utc)
    session.add(
        ContentCandidate(
            id=candidate_id,
            competition_slug="tercera_rfef_g11",
            content_type=content_type,
            priority=priority,
            text_draft=text_draft,
            payload_json=payload_json,
            source_summary_hash=f"story-importance-{candidate_id}",
            scheduled_at=None,
            status=status,
            reviewed_at=timestamp if status != "draft" else None,
            approved_at=timestamp if status != "draft" else None,
            published_at=timestamp if published else None,
            external_publication_ref=external_ref,
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    session.commit()


def test_story_importance_prioritizes_stronger_content_types() -> None:
    session = build_session()
    try:
        seed_competition(session)
        add_candidate(
            session,
            candidate_id=1,
            content_type="standings_event",
            priority=79,
            text_draft="Nuevo lider en 3a RFEF Baleares: CD Alpha pasa del 2º al 1º.",
            payload_json={
                "content_key": "standings_event:new_leader:alpha",
                "source_payload": {
                    "event_type": "new_leader",
                    "team": "CD Alpha",
                    "teams": ["CD Alpha"],
                    "previous_position": 2,
                    "current_position": 1,
                    "position_delta": 1,
                },
            },
        )
        add_candidate(
            session,
            candidate_id=2,
            content_type="results_roundup",
            priority=99,
            text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 26\n\nCD Alpha 2-0 CD Beta\nCD Gamma 1-0 CD Delta",
            payload_json={
                "content_key": "results_roundup:j26",
                "source_payload": {
                    "selected_matches_count": 2,
                    "omitted_matches_count": 0,
                    "matches": [
                        {"home_team": "CD Alpha", "away_team": "CD Beta"},
                        {"home_team": "CD Gamma", "away_team": "CD Delta"},
                    ],
                },
            },
        )
        add_candidate(
            session,
            candidate_id=3,
            content_type="preview",
            priority=90,
            text_draft="Previa simple.",
            payload_json={"content_key": "preview:j26", "source_payload": {}},
        )
        add_candidate(
            session,
            candidate_id=4,
            content_type="ranking",
            priority=70,
            text_draft="Ranking editorial simple.",
            payload_json={"content_key": "ranking:j26", "source_payload": {}},
        )

        rows = StoryImportanceService(session, settings=build_settings()).top_for_date(limit=10).rows

        assert [row.candidate_id for row in rows[:4]] == [1, 2, 3, 4]
        assert rows[0].priority_bucket in {"high", "critical"}
    finally:
        session.close()


def test_story_importance_scores_strong_event_above_weaker_event() -> None:
    session = build_session()
    try:
        seed_competition(session)
        add_candidate(
            session,
            candidate_id=10,
            content_type="viral_story",
            priority=76,
            text_draft="CD Alpha llega con 5 victorias seguidas.",
            payload_json={
                "content_key": "viral:win_streak:alpha",
                "source_payload": {
                    "story_type": "win_streak",
                    "team": "CD Alpha",
                    "teams": ["CD Alpha"],
                    "metric_value": 5,
                    "streak_length": 5,
                },
            },
        )
        add_candidate(
            session,
            candidate_id=11,
            content_type="standings_event",
            priority=73,
            text_draft="La mayor subida la firma CD Beta: del 7º al 5º.",
            payload_json={
                "content_key": "standings_event:rise:beta",
                "source_payload": {
                    "event_type": "biggest_position_rise",
                    "team": "CD Beta",
                    "teams": ["CD Beta"],
                    "previous_position": 7,
                    "current_position": 5,
                    "position_delta": 2,
                },
            },
        )

        strong = StoryImportanceService(session, settings=build_settings()).score_candidate(10).candidate
        weak = StoryImportanceService(session, settings=build_settings()).score_candidate(11).candidate

        assert strong.importance_score > weak.importance_score
        assert any(reason.startswith("viral_story:win_streak") for reason in strong.importance_reasoning)
    finally:
        session.close()


def test_story_importance_applies_repetition_penalty() -> None:
    session = build_session()
    try:
        seed_competition(session)
        add_candidate(
            session,
            candidate_id=20,
            content_type="viral_story",
            priority=76,
            text_draft="CD Alpha llega con 4 victorias seguidas.",
            payload_json={
                "content_key": "viral:win_streak:alpha",
                "source_payload": {
                    "story_type": "win_streak",
                    "team": "CD Alpha",
                    "teams": ["CD Alpha"],
                    "metric_value": 4,
                    "streak_length": 4,
                },
            },
        )
        add_candidate(
            session,
            candidate_id=21,
            content_type="viral_story",
            priority=76,
            text_draft="CD Alpha sostiene una racha de 4 victorias seguidas.",
            payload_json={
                "content_key": "viral:win_streak:alpha",
                "source_payload": {
                    "story_type": "win_streak",
                    "team": "CD Alpha",
                    "teams": ["CD Alpha"],
                    "metric_value": 4,
                    "streak_length": 4,
                },
            },
        )

        candidate = StoryImportanceService(session, settings=build_settings()).score_candidate(21).candidate

        assert any(reason.startswith("repetition_penalty") for reason in candidate.importance_reasoning)
        assert "repeat_content_key" in candidate.tags
    finally:
        session.close()


def test_story_importance_rank_pending_orders_by_score_and_skips_exported() -> None:
    session = build_session()
    try:
        seed_competition(session)
        add_candidate(
            session,
            candidate_id=30,
            content_type="featured_match_preview",
            priority=95,
            text_draft="Partido destacado del fin de semana.",
            payload_json={
                "content_key": "featured_match_preview:alpha-beta",
                "source_payload": {
                    "home_team": "CD Alpha",
                    "away_team": "CD Beta",
                    "importance_score": 92,
                    "tags": ["title_race", "hot_form_match", "direct_rivalry"],
                    "home_recent_points": 13,
                    "away_recent_points": 11,
                },
            },
        )
        add_candidate(
            session,
            candidate_id=31,
            content_type="results_roundup",
            priority=99,
            text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 26\n\nCD Alpha 2-0 CD Beta",
            payload_json={
                "content_key": "results_roundup:j26",
                "source_payload": {
                    "selected_matches_count": 1,
                    "omitted_matches_count": 0,
                    "matches": [{"home_team": "CD Alpha", "away_team": "CD Beta"}],
                },
            },
        )
        add_candidate(
            session,
            candidate_id=32,
            content_type="ranking",
            priority=70,
            text_draft="Ranking editorial simple.",
            payload_json={"content_key": "ranking:j26", "source_payload": {}},
            external_ref="legacy-export-32",
        )

        rows = StoryImportanceService(session, settings=build_settings()).rank_pending(limit=10).rows

        assert [row.candidate_id for row in rows[:2]] == [30, 31]
        assert all(row.candidate_id != 32 for row in rows)
    finally:
        session.close()


def test_story_importance_selects_only_critical_narratives() -> None:
    session = build_session()
    try:
        seed_competition(session)
        add_candidate(
            session,
            candidate_id=40,
            content_type="standings_event",
            priority=96,
            text_draft="Nuevo lider en 3a RFEF Baleares: CD Alpha pasa al 1º puesto.",
            payload_json={
                "content_key": "standings_event:new_leader:alpha",
                "source_payload": {
                    "event_type": "new_leader",
                    "team": "CD Alpha",
                    "teams": ["CD Alpha"],
                    "previous_position": 2,
                    "current_position": 1,
                    "position_delta": 1,
                },
            },
            status="draft",
            published=False,
        )
        add_candidate(
            session,
            candidate_id=41,
            content_type="viral_story",
            priority=82,
            text_draft="CD Beta llega con 3 victorias seguidas.",
            payload_json={
                "content_key": "viral:win_streak:beta",
                "source_payload": {
                    "story_type": "win_streak",
                    "team": "CD Beta",
                    "teams": ["CD Beta"],
                    "metric_value": 3,
                    "streak_length": 3,
                },
            },
            status="draft",
            published=False,
        )

        decisions = StoryImportanceService(session, settings=build_settings()).select_automatic_narratives(
            [session.get(ContentCandidate, 40), session.get(ContentCandidate, 41)]
        )

        assert decisions[40].allowed is True
        assert decisions[40].priority_bucket == "critical"
        assert decisions[41].allowed is False
        assert decisions[41].reason.startswith("below_threshold:")
    finally:
        session.close()
