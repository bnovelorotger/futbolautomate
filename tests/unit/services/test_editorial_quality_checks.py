from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import ContentCandidate
from app.services.editorial_narratives import EditorialNarrativesService
from app.services.editorial_quality_checks import EditorialQualityChecksService
from app.services.editorial_viral_stories import EditorialViralStoriesService
from tests.unit.services.test_editorial_narratives import build_session, seed_narratives_data
from tests.unit.services.test_typefully_autoexport_service import build_policy
from tests.unit.services.test_typefully_export_service import build_settings


def test_quality_checks_pass_for_valid_generated_viral_story() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        service = EditorialViralStoriesService(session)
        service.generate_for_competition("tercera_rfef_g11")
        candidate = session.query(ContentCandidate).filter_by(content_type="viral_story").first()
        assert candidate is not None
        candidate.status = "published"
        candidate.published_at = datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc)
        session.add(candidate)
        session.commit()

        result = EditorialQualityChecksService(
            session,
            settings=build_settings(),
            policy=build_policy(enabled=True),
        ).check_candidate(candidate.id, dry_run=False)
        session.commit()

        reloaded = session.get(ContentCandidate, candidate.id)
        assert result.candidate.passed is True
        assert reloaded.quality_check_passed is True
        assert reloaded.quality_check_errors == []
        assert reloaded.quality_checked_at is not None
    finally:
        session.close()


def test_quality_checks_block_trivial_viral_story() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        candidate = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="viral_story",
            priority=70,
            text_draft="CD Llosetense llega con 2 victorias seguidas en 3a RFEF Baleares.",
            payload_json={
                "content_key": "viral:win_streak:cd-llosetense:manual",
                "source_payload": {
                    "story_type": "win_streak",
                    "title": "Racha de victorias de CD Llosetense",
                    "teams": ["CD Llosetense"],
                    "metric_value": 2,
                    "streak_length": 2,
                },
            },
            source_summary_hash="quality-trivial-viral",
            scheduled_at=None,
            status="published",
            reviewed_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
            approved_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
        )
        session.add(candidate)
        session.commit()

        result = EditorialQualityChecksService(
            session,
            settings=build_settings(),
            policy=build_policy(enabled=True),
        ).check_candidate(candidate.id, dry_run=False)

        assert result.candidate.passed is False
        assert any(error.startswith("viral_story_below_threshold") for error in result.candidate.errors)
    finally:
        session.close()


def test_quality_checks_block_recent_duplicates() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        first = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="metric_narrative",
            priority=68,
            text_draft="CD Llosetense suma 3 victorias consecutivas en 3a RFEF Baleares.",
            payload_json={
                "content_key": "metric:win_streak:cd-llosetense:a",
                "source_payload": {
                    "narrative_type": "win_streak",
                    "team": "CD Llosetense",
                    "teams": ["CD Llosetense"],
                    "metric_value": 3,
                },
            },
            source_summary_hash="quality-duplicate-a",
            status="published",
            reviewed_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
            approved_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
        )
        second = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="metric_narrative",
            priority=68,
            text_draft="CD Llosetense suma 3 victorias consecutivas en 3a RFEF Baleares.",
            payload_json={
                "content_key": "metric:win_streak:cd-llosetense:b",
                "source_payload": {
                    "narrative_type": "win_streak",
                    "team": "CD Llosetense",
                    "teams": ["CD Llosetense"],
                    "metric_value": 3,
                },
            },
            source_summary_hash="quality-duplicate-b",
            status="published",
            reviewed_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
            approved_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
        )
        session.add_all([first, second])
        session.commit()

        result = EditorialQualityChecksService(
            session,
            settings=build_settings(),
            policy=build_policy(enabled=True),
        ).check_candidate(second.id, dry_run=False)

        assert result.candidate.passed is False
        assert any(error.startswith("duplicate_recent_") for error in result.candidate.errors)
    finally:
        session.close()


def test_quality_checks_persist_errors_for_invalid_stat_narrative() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        EditorialNarrativesService(session).generate_for_competition("tercera_rfef_g11")
        candidate = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="stat_narrative",
            priority=60,
            text_draft="NARRATIVA ESTADISTICA\n\nDato base sin payload suficiente",
            payload_json={"content_key": "stat:broken", "source_payload": {}},
            source_summary_hash="quality-bad-stat",
            status="published",
            reviewed_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
            approved_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
        )
        session.add(candidate)
        session.commit()

        EditorialQualityChecksService(
            session,
            settings=build_settings(),
            policy=build_policy(enabled=True),
        ).check_candidate(candidate.id, dry_run=False)
        session.commit()

        reloaded = session.get(ContentCandidate, candidate.id)
        assert reloaded.quality_check_passed is False
        assert "stat_narrative_payload_incomplete" in (reloaded.quality_check_errors or [])
        assert reloaded.quality_checked_at is not None
    finally:
        session.close()
