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


def test_quality_checks_pass_for_valid_results_roundup() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        candidate = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="results_roundup",
            priority=99,
            text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 12\n\nCD Llosetense 2-0 SD Portmany\nCE Mercadal 1-2 CD Manacor",
            payload_json={
                "content_key": "results_roundup:j12",
                "source_payload": {
                    "group_label": "Jornada 12",
                    "selected_matches_count": 2,
                    "omitted_matches_count": 0,
                    "matches": [
                        {"home_team": "CD Llosetense", "away_team": "SD Portmany", "home_score": 2, "away_score": 0},
                        {"home_team": "CE Mercadal", "away_team": "CD Manacor", "home_score": 1, "away_score": 2},
                    ],
                },
            },
            source_summary_hash="quality-good-roundup",
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

        assert result.candidate.passed is True
        assert result.candidate.errors == []
    finally:
        session.close()


def test_quality_checks_accept_results_roundup_with_normalized_team_names() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        candidate = ContentCandidate(
            competition_slug="segunda_rfef_g3_baleares",
            content_type="results_roundup",
            priority=99,
            text_draft="RESULTADOS | 2a RFEF con equipos baleares | Jornada 26\n\nAtletico Baleares 2-0 Torrent CF",
            payload_json={
                "content_key": "results_roundup:j26",
                "source_payload": {
                    "group_label": "Jornada 26",
                    "selected_matches_count": 1,
                    "omitted_matches_count": 0,
                    "matches": [
                        {
                            "home_team": "Atletico Baleares",
                            "away_team": "Torrent CF",
                            "home_score": 2,
                            "away_score": 0,
                        }
                    ],
                },
            },
            source_summary_hash="quality-normalized-teams",
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

        assert result.candidate.passed is True
        assert result.candidate.errors == []
    finally:
        session.close()


def test_quality_checks_accept_standings_roundup_multiline_format() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        candidate = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="standings_roundup",
            priority=82,
            text_draft="📊 CLASIFICACION\n\n3a RFEF Baleares\n\n1️⃣ CD Llosetense - 54 [PO]\n2️⃣ CD Manacor - 52 [PO]\n3️⃣ CE Mercadal - 50 [PO]\n4️⃣ SD Portmany - 47 [PO]\n5. CD Llosetense - 24 [DESC]\n6. CD Manacor - 21 [DESC]\n\n#TerceraRFEF",
            payload_json={
                "content_key": "standings_roundup:j26",
                "source_payload": {
                    "selected_rows_count": 6,
                    "omitted_rows_count": 9,
                    "rows": [
                        {"position": 1, "team": "CD Llosetense", "points": 54},
                        {"position": 2, "team": "CD Manacor", "points": 52, "zone_tag": "playoff"},
                        {"position": 3, "team": "CE Mercadal", "points": 50, "zone_tag": "playoff"},
                        {"position": 4, "team": "SD Portmany", "points": 47, "zone_tag": "playoff"},
                        {"position": 5, "team": "CD Llosetense", "points": 24, "zone_tag": "relegation"},
                        {"position": 6, "team": "CD Manacor", "points": 21, "zone_tag": "relegation"},
                    ],
                },
            },
            source_summary_hash="quality-standings-roundup",
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

        assert result.candidate.passed is True
        assert result.candidate.errors == []
    finally:
        session.close()


def test_quality_checks_block_standings_roundup_without_rows_payload() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        candidate = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="standings_roundup",
            priority=82,
            text_draft="CLASIFICACION | 3a RFEF Baleares\n\n1. CD Llosetense - 54 pts",
            payload_json={
                "content_key": "standings_roundup:broken",
                "source_payload": {
                    "group_label": "Jornada 26",
                },
            },
            source_summary_hash="quality-standings-roundup-broken",
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
        assert "standings_roundup_rows_missing" in result.candidate.errors
        assert "standings_roundup_selected_rows_count_missing" in result.candidate.errors
    finally:
        session.close()


def test_quality_checks_only_block_newer_duplicate_roundup() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        first = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="results_roundup",
            priority=99,
            text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 26\n\nCD Llosetense 2-0 SD Portmany",
            payload_json={
                "content_key": "results_roundup:j26:a",
                "source_payload": {
                    "group_label": "Jornada 26",
                    "selected_matches_count": 1,
                    "omitted_matches_count": 0,
                    "matches": [
                        {"home_team": "CD Llosetense", "away_team": "SD Portmany", "home_score": 2, "away_score": 0}
                    ],
                },
            },
            source_summary_hash="quality-duplicate-roundup-a",
            status="published",
            created_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
            reviewed_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
            approved_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
        )
        second = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="results_roundup",
            priority=99,
            text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 26\n\nCD Llosetense 2-0 SD Portmany",
            payload_json={
                "content_key": "results_roundup:j26:b",
                "source_payload": {
                    "group_label": "Jornada 26",
                    "selected_matches_count": 1,
                    "omitted_matches_count": 0,
                    "matches": [
                        {"home_team": "CD Llosetense", "away_team": "SD Portmany", "home_score": 2, "away_score": 0}
                    ],
                },
            },
            source_summary_hash="quality-duplicate-roundup-b",
            status="published",
            created_at=datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc),
            reviewed_at=datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc),
            approved_at=datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc),
        )
        session.add_all([first, second])
        session.commit()

        service = EditorialQualityChecksService(
            session,
            settings=build_settings(),
            policy=build_policy(enabled=True),
        )
        first_result = service.check_candidate(first.id, dry_run=False)
        second_result = service.check_candidate(second.id, dry_run=False)

        assert first_result.candidate.passed is True
        assert second_result.candidate.passed is False
        assert "duplicate_recent_text" in second_result.candidate.errors
    finally:
        session.close()


def test_quality_checks_keep_older_roundup_valid_after_publish_state_changes() -> None:
    session = build_session()
    try:
        seed_narratives_data(session)
        first = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="standings_roundup",
            priority=82,
            text_draft="CLASIFICACION | 3a RFEF Baleares\n\n1. CD Llosetense - 54 pts",
            payload_json={
                "content_key": "standings_roundup:j26:a",
                "source_payload": {
                    "group_label": "Jornada 26",
                    "selected_rows_count": 1,
                    "omitted_rows_count": 0,
                    "rows": [{"position": 1, "team": "CD Llosetense", "points": 54}],
                },
            },
            source_summary_hash="quality-standings-duplicate-a",
            status="published",
            created_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
            reviewed_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            approved_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
        )
        second = ContentCandidate(
            competition_slug="tercera_rfef_g11",
            content_type="standings_roundup",
            priority=82,
            text_draft="CLASIFICACION | 3a RFEF Baleares\n\n1. CD Llosetense - 54 pts",
            payload_json={
                "content_key": "standings_roundup:j26:b",
                "source_payload": {
                    "group_label": "Jornada 26",
                    "selected_rows_count": 1,
                    "omitted_rows_count": 0,
                    "rows": [{"position": 1, "team": "CD Llosetense", "points": 54}],
                },
            },
            source_summary_hash="quality-standings-duplicate-b",
            status="draft",
            created_at=datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc),
        )
        session.add_all([first, second])
        session.commit()

        result = EditorialQualityChecksService(
            session,
            settings=build_settings(),
            policy=build_policy(enabled=True),
        ).check_candidate(first.id, dry_run=False)

        assert result.candidate.passed is True
        assert result.candidate.errors == []
    finally:
        session.close()
