from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from app.db.models import ContentCandidate
from app.services.editorial_approval_policy import EditorialApprovalPolicyService
from app.services.editorial_release_pipeline import EditorialReleasePipelineService
from app.services.x_browser_publication_service import XBrowserBatchResult, XBrowserPublicationService
from app.services.x_publication_scheduler import XPublicationScheduler
from tests.unit.services.service_test_support import build_session, build_settings
from tests.unit.services.test_editorial_narratives import seed_competition

REFERENCE_DATE = date(2026, 3, 17)
WEDNESDAY_REFERENCE_DATE = date(2026, 3, 18)


def seed_release_candidates(session) -> None:
    created_at = datetime(2026, 3, 17, 10, 0, tzinfo=UTC)
    match_date = date(2026, 3, 16)
    seed_competition(
        session,
        code="tercera_rfef_g11",
        name="3a RFEF Grupo 11",
        teams=["CD Llosetense", "SD Portmany", "CE Mercadal", "RCD Mallorca B", "CD Manacor"],
        standings_rows=[
            {"position": 1, "team": "RCD Mallorca B", "played": 26, "wins": 18, "draws": 4, "losses": 4, "goals_for": 55, "goals_against": 20, "goal_difference": 35, "points": 58},
            {"position": 2, "team": "CD Llosetense", "played": 26, "wins": 16, "draws": 5, "losses": 5, "goals_for": 44, "goals_against": 21, "goal_difference": 23, "points": 53},
            {"position": 3, "team": "SD Portmany", "played": 26, "wins": 15, "draws": 4, "losses": 7, "goals_for": 39, "goals_against": 24, "goal_difference": 15, "points": 49},
            {"position": 4, "team": "CE Mercadal", "played": 26, "wins": 14, "draws": 4, "losses": 8, "goals_for": 35, "goals_against": 28, "goal_difference": 7, "points": 46},
            {"position": 5, "team": "CD Manacor", "played": 26, "wins": 13, "draws": 5, "losses": 8, "goals_for": 33, "goals_against": 26, "goal_difference": 7, "points": 44},
        ],
        match_rows=[
            {"round_name": "Jornada 26", "match_date": match_date, "match_time": created_at.time(), "home_team": "CD Llosetense", "away_team": "SD Portmany", "home_score": 2, "away_score": 0},
            {"round_name": "Jornada 26", "match_date": match_date, "match_time": created_at.time(), "home_team": "CD Manacor", "away_team": "CE Mercadal", "home_score": 2, "away_score": 1},
        ],
    )
    session.add_all(
        [
            ContentCandidate(
                id=101,
                competition_slug="tercera_rfef_g11",
                content_type="match_result",
                priority=100,
                text_draft="RESULTADO FINAL\n\nCD Llosetense 2-0 SD Portmany",
                payload_json={"reference_date": REFERENCE_DATE.isoformat(), "source_payload": {"match_date": match_date.isoformat(), "round_name": "Jornada 26"}},
                source_summary_hash="release-hash-101",
                scheduled_at=None,
                status="draft",
                created_at=created_at,
                updated_at=created_at,
            ),
            ContentCandidate(
                id=102,
                competition_slug="tercera_rfef_g11",
                content_type="standings_roundup",
                priority=80,
                text_draft=(
                    "CLASIFICACION | 3a RFEF Grupo 11 | Jornada 26 (1/2)\n\n"
                    "1. RCD Mallorca B - 58 pts\n"
                    "2. CD Llosetense - 53 pts [PO]\n"
                    "3. SD Portmany - 49 pts [PO]\n"
                    "4. CE Mercadal - 46 pts [PO]"
                ),
                payload_json={
                    "reference_date": REFERENCE_DATE.isoformat(),
                    "content_key": "standings_roundup:j26",
                    "source_payload": {
                        "group_label": "Jornada 26",
                        "part_index": 1,
                        "part_total": 2,
                        "split_focus": "top",
                        "selected_rows_count": 4,
                        "omitted_rows_count": 1,
                        "rows": [
                            {"position": 1, "team": "RCD Mallorca B", "points": 58},
                            {"position": 2, "team": "CD Llosetense", "points": 53, "zone_tag": "playoff"},
                            {"position": 3, "team": "SD Portmany", "points": 49, "zone_tag": "playoff"},
                            {"position": 4, "team": "CE Mercadal", "points": 46, "zone_tag": "playoff"},
                        ],
                    },
                },
                source_summary_hash="release-hash-102",
                scheduled_at=None,
                status="draft",
                created_at=created_at,
                updated_at=created_at,
            ),
            ContentCandidate(
                id=109,
                competition_slug="tercera_rfef_g11",
                content_type="standings_roundup",
                priority=79,
                text_draft=(
                    "CLASIFICACION | 3a RFEF Grupo 11 | Jornada 26 (2/2)\n\n"
                    "14. CD Llosetense - 28 pts [DESC]\n"
                    "15. SD Portmany - 24 pts [DESC]"
                ),
                payload_json={
                    "reference_date": REFERENCE_DATE.isoformat(),
                    "content_key": "standings_roundup:j26:relegation",
                    "source_payload": {
                        "group_label": "Jornada 26",
                        "round_name": "Jornada 26",
                        "part_index": 2,
                        "part_total": 2,
                        "split_focus": "relegation",
                        "selected_rows_count": 2,
                        "omitted_rows_count": 4,
                        "rows": [
                            {"position": 14, "team": "CD Llosetense", "played": 26, "points": 28, "zone_tag": "relegation"},
                            {"position": 15, "team": "SD Portmany", "played": 26, "points": 24, "zone_tag": "relegation"},
                        ],
                    },
                },
                source_summary_hash="release-hash-109",
                scheduled_at=None,
                status="draft",
                created_at=created_at,
                updated_at=created_at,
            ),
            ContentCandidate(
                id=106,
                competition_slug="tercera_rfef_g11",
                content_type="results_roundup",
                priority=99,
                text_draft=(
                    "RESULTADOS | 3a RFEF Baleares | Jornada 26\n\n"
                    "CD Llosetense 2-0 SD Portmany\n"
                    "CD Manacor 2-1 CE Mercadal"
                ),
                payload_json={
                    "reference_date": REFERENCE_DATE.isoformat(),
                    "content_key": "results_roundup:j26",
                    "source_payload": {
                        "group_label": "Jornada 26",
                        "selected_matches_count": 2,
                        "omitted_matches_count": 0,
                        "matches": [
                            {"round_name": "Jornada 26", "match_date": match_date.isoformat(), "home_team": "CD Llosetense", "away_team": "SD Portmany", "home_score": 2, "away_score": 0},
                            {"round_name": "Jornada 26", "match_date": match_date.isoformat(), "home_team": "CD Manacor", "away_team": "CE Mercadal", "home_score": 2, "away_score": 1},
                        ],
                    },
                },
                source_summary_hash="release-hash-106",
                scheduled_at=None,
                status="draft",
                created_at=created_at,
                updated_at=created_at,
            ),
            ContentCandidate(
                id=103,
                competition_slug="tercera_rfef_g11",
                content_type="viral_story",
                priority=70,
                text_draft="CD Manacor llega con 3 victorias seguidas en 3a RFEF Baleares.",
                payload_json={
                    "reference_date": REFERENCE_DATE.isoformat(),
                    "content_key": "viral:win_streak:cd-manacor",
                    "source_payload": {
                        "story_type": "win_streak",
                        "teams": ["CD Manacor"],
                        "streak_length": 3,
                        "metric_value": 3,
                    },
                },
                source_summary_hash="release-hash-103",
                scheduled_at=None,
                status="draft",
                created_at=created_at,
                updated_at=created_at,
            ),
            ContentCandidate(
                id=104,
                competition_slug="tercera_rfef_g11",
                content_type="preview",
                priority=90,
                text_draft="   ",
                payload_json={"reference_date": REFERENCE_DATE.isoformat(), "source_payload": {}},
                source_summary_hash="release-hash-104",
                scheduled_at=None,
                status="draft",
                created_at=created_at,
                updated_at=created_at,
            ),
        ]
    )
    session.commit()


def add_critical_narrative_candidates(session) -> None:
    created_at = datetime(2026, 3, 17, 10, 2, tzinfo=UTC)
    session.add_all(
        [
            ContentCandidate(
                id=107,
                competition_slug="tercera_rfef_g11",
                content_type="featured_match_event",
                priority=96,
                text_draft="Pulso por el liderato en 3a RFEF Baleares: CD Llosetense y RCD Mallorca B llegan a la zona alta.",
                payload_json={
                    "reference_date": REFERENCE_DATE.isoformat(),
                    "content_key": "featured_match_event:llosetense-mallorca-b:top",
                    "source_payload": {
                        "round_name": "Jornada 27",
                        "match_date": "2026-03-21",
                        "home_team": "CD Llosetense",
                        "away_team": "RCD Mallorca B",
                        "teams": ["CD Llosetense", "RCD Mallorca B"],
                        "importance_score": 92,
                        "tags": ["title_race", "hot_form_match", "direct_rivalry"],
                        "home_recent_points": 11,
                        "away_recent_points": 13,
                    },
                },
                source_summary_hash="release-hash-107",
                scheduled_at=None,
                status="draft",
                created_at=created_at,
                updated_at=created_at,
            ),
            ContentCandidate(
                id=108,
                competition_slug="tercera_rfef_g11",
                content_type="viral_story",
                priority=94,
                text_draft="CD Manacor llega con 3 victorias seguidas en 3a RFEF Baleares.",
                payload_json={
                    "reference_date": REFERENCE_DATE.isoformat(),
                    "content_key": "viral:win_streak:cd-manacor:release",
                    "source_payload": {
                        "story_type": "win_streak",
                        "team": "CD Manacor",
                        "teams": ["CD Manacor"],
                        "metric_value": 3,
                        "streak_length": 3,
                    },
                },
                source_summary_hash="release-hash-108",
                scheduled_at=None,
                status="draft",
                created_at=created_at,
                updated_at=created_at,
            ),
        ]
    )
    session.commit()


def add_quality_blocked_candidate(session) -> None:
    created_at = datetime(2026, 3, 17, 10, 1, tzinfo=UTC)
    session.add(
        ContentCandidate(
            id=105,
            competition_slug="tercera_rfef_g11",
            content_type="preview",
            priority=85,
            text_draft="P" * 400,
            payload_json={"reference_date": REFERENCE_DATE.isoformat(), "source_payload": {}},
            source_summary_hash="release-hash-105",
            scheduled_at=None,
            status="draft",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.commit()


def add_future_preview_candidate(session) -> None:
    created_at = datetime(2026, 3, 17, 10, 3, tzinfo=UTC)
    session.add(
        ContentCandidate(
            id=110,
            competition_slug="tercera_rfef_g11",
            content_type="preview",
            priority=90,
            text_draft=(
                "PREVIA DE LA JORNADA\n\n"
                "3a RFEF Grupo 11\n\n"
                "Jornada 27 | domingo, 21 de marzo de 2099 | CD Llosetense vs SD Portmany\n\n"
                "Partido destacado: CD Llosetense vs SD Portmany"
            ),
            payload_json={
                "reference_date": REFERENCE_DATE.isoformat(),
                "content_key": "preview:j27:future",
                "source_payload": {
                    "featured_match": {
                        "round_name": "Jornada 27",
                        "match_date": "2099-03-21",
                        "home_team": "CD Llosetense",
                        "away_team": "SD Portmany",
                    },
                    "matches": [
                        {
                            "round_name": "Jornada 27",
                            "match_date": "2099-03-21",
                            "home_team": "CD Llosetense",
                            "away_team": "SD Portmany",
                        }
                    ],
                },
            },
            source_summary_hash="release-hash-110",
            scheduled_at=datetime(2099, 3, 21, 12, 0, tzinfo=UTC),
            status="draft",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.commit()


def add_ready_approved_preview_candidate(session) -> None:
    created_at = datetime(2026, 3, 15, 10, 3, tzinfo=UTC)
    session.add(
        ContentCandidate(
            id=111,
            competition_slug="tercera_rfef_g11",
            content_type="preview",
            priority=88,
            text_draft=(
                "PREVIA DE LA JORNADA\n\n"
                "3a RFEF Grupo 11\n\n"
                "Jornada 27 | viernes, 19 de marzo de 2026 | CD Llosetense vs SD Portmany\n\n"
                "Partido destacado: CD Llosetense vs SD Portmany"
            ),
            payload_json={
                "reference_date": "2026-03-10",
                "content_key": "preview:j27:ready-approved",
                "source_payload": {
                    "featured_match": {
                        "round_name": "Jornada 27",
                        "match_date": "2026-03-19",
                        "home_team": "CD Llosetense",
                        "away_team": "SD Portmany",
                    },
                    "matches": [
                        {
                            "round_name": "Jornada 27",
                            "match_date": "2026-03-19",
                            "home_team": "CD Llosetense",
                            "away_team": "SD Portmany",
                        }
                    ],
                },
            },
            source_summary_hash="release-hash-111",
            scheduled_at=None,
            status="approved",
            reviewed_at=created_at,
            approved_at=created_at,
            autoapproved=True,
            autoapproved_at=created_at,
            autoapproval_reason="policy_autoapprove_safe_type",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.commit()


def seed_wednesday_browser_backlog(session, *, valid_count: int = 47, blocked_count: int = 6) -> list[int]:
    created_at = datetime(2026, 3, 18, 18, 30, tzinfo=UTC)
    match_date = date(2026, 3, 17)
    seed_competition(
        session,
        code="tercera_rfef_g11",
        name="3a RFEF Grupo 11",
        teams=["CD Llosetense", "SD Portmany", "CE Mercadal", "RCD Mallorca B", "CD Manacor"],
        standings_rows=[
            {"position": 1, "team": "RCD Mallorca B", "played": 26, "wins": 18, "draws": 4, "losses": 4, "goals_for": 55, "goals_against": 20, "goal_difference": 35, "points": 58},
            {"position": 2, "team": "CD Llosetense", "played": 26, "wins": 16, "draws": 5, "losses": 5, "goals_for": 44, "goals_against": 21, "goal_difference": 23, "points": 53},
        ],
        match_rows=[
            {"round_name": "Jornada 26", "match_date": match_date, "match_time": created_at.time(), "home_team": "CD Llosetense", "away_team": "SD Portmany", "home_score": 2, "away_score": 0},
        ],
    )
    blocked_candidates = [
        ContentCandidate(
            id=1900 + index,
            competition_slug="tercera_rfef_g11",
            content_type="results_roundup",
            priority=999 - index,
            text_draft=f"Playoff bloqueado {index}\n\nCD Llosetense 2-0 SD Portmany",
            payload_json={
                "reference_date": WEDNESDAY_REFERENCE_DATE.isoformat(),
                "content_key": f"blocked-results-{index}",
                "source_payload": {
                    "group_label": "Jornada 26",
                    "matches": [
                        {
                            "round_name": "Jornada 26",
                            "match_date": match_date.isoformat(),
                            "home_team": "CD Llosetense",
                            "away_team": "SD Portmany",
                            "home_score": 2,
                            "away_score": 0,
                        }
                    ],
                },
            },
            source_summary_hash=f"blocked-results-{index}",
            scheduled_at=None,
            status="draft",
            created_at=created_at,
            updated_at=created_at,
        )
        for index in range(blocked_count)
    ]
    valid_ids = [2000 + index for index in range(valid_count)]
    valid_candidates = [
        ContentCandidate(
            id=candidate_id,
            competition_slug="tercera_rfef_g11",
            content_type="viral_story",
            priority=800 - index,
            text_draft=f"Racha caliente {index}: cinco victorias seguidas en 3a RFEF Baleares.",
            payload_json={
                "reference_date": WEDNESDAY_REFERENCE_DATE.isoformat(),
                "content_key": f"viral-win-streak-{index}",
                "source_payload": {
                    "story_type": "win_streak",
                    "streak_length": 5,
                    "metric_value": 5,
                },
            },
            source_summary_hash=f"viral-win-streak-{index}",
            scheduled_at=None,
            status="draft",
            created_at=created_at,
            updated_at=created_at,
        )
        for index, candidate_id in enumerate(valid_ids)
    ]
    session.add_all([*blocked_candidates, *valid_candidates])
    session.commit()
    return valid_ids


def build_release_service(session, tmp_path: Path) -> EditorialReleasePipelineService:
    return EditorialReleasePipelineService(
        session,
        settings=build_settings(app_root=tmp_path),
    )


def build_release_service_with_legacy_export(session, tmp_path: Path) -> EditorialReleasePipelineService:
    return EditorialReleasePipelineService(
        session,
        settings=build_settings(app_root=tmp_path, legacy_export_json_enabled=True),
    )


def test_editorial_approval_policy_marks_safe_types_and_blocks_sensitive(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        result = EditorialApprovalPolicyService(
            session,
            settings=build_settings(app_root=tmp_path),
        ).autoapprove(reference_date=REFERENCE_DATE, dry_run=True)

        rows = {row.id: row for row in result.rows}
        assert result.drafts_found == 6
        assert result.autoapprovable_count == 4
        assert result.manual_review_count == 2
        assert rows[101].autoapprovable is False
        assert rows[101].policy_reason == "manual_review_policy"
        assert rows[102].autoapprovable is True
        assert rows[109].autoapprovable is True
        assert rows[106].autoapprovable is True
        assert rows[103].autoapprovable is True
        assert rows[103].policy_reason == "policy_autoapprove_safe_type"
        assert rows[104].autoapprovable is False
        assert rows[104].policy_reason == "text_draft_empty"
    finally:
        session.close()


def test_editorial_approval_policy_blocks_narratives_with_quality_errors(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        add_critical_narrative_candidates(session)

        result = EditorialApprovalPolicyService(
            session,
            settings=build_settings(app_root=tmp_path),
        ).autoapprove(reference_date=REFERENCE_DATE, dry_run=True)

        rows = {row.id: row for row in result.rows}
        assert rows[107].autoapprovable is False
        assert rows[107].policy_reason == "manual_review_policy"
        assert rows[108].autoapprovable is False
        assert rows[108].policy_reason == "quality_errors_present"
    finally:
        session.close()


def test_editorial_release_pipeline_real_run_generates_export_base_snapshot(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        add_quality_blocked_candidate(session)
        service = build_release_service(session, tmp_path)

        result = service.run(reference_date=REFERENCE_DATE, dry_run=False)
        session.commit()

        export_path = tmp_path / "exports" / "export_base.json"
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        assert result.drafts_found == 7
        assert result.autoapprovable_count == 4
        assert result.autoapproved_count == 4
        assert result.manual_review_count == 3
        assert result.dispatched_count == 4
        assert result.export_base_total_items == 4
        assert result.export_base_path == str(export_path)
        assert result.legacy_export_json_count == 0
        assert result.legacy_export_blocked_series_count == 0
        assert result.legacy_export_json_path is None
        assert payload["scope"] == "weekly_snapshot"
        assert payload["total_items"] == 4
        assert set(payload["competitions"]) == {"tercera_rfef_g11"}
        assert set(payload["competitions"]["tercera_rfef_g11"]) == {
            "results_roundup",
            "standings_roundup",
            "viral_story",
        }
        exported_ids = {
            item["id"]
            for items in payload["competitions"]["tercera_rfef_g11"].values()
            for item in items
        }
        assert exported_ids == {102, 103, 106, 109}
        assert not (tmp_path / "export" / "legacy_export.json").exists()
        assert session.get(ContentCandidate, 101).status == "draft"
        assert session.get(ContentCandidate, 102).status == "published"
        assert session.get(ContentCandidate, 109).status == "published"
        assert session.get(ContentCandidate, 106).status == "published"
        assert session.get(ContentCandidate, 103).status == "published"
        assert session.get(ContentCandidate, 104).status == "draft"
        assert session.get(ContentCandidate, 105).status == "draft"
        assert session.get(ContentCandidate, 105).quality_check_passed is False
    finally:
        session.close()


def test_editorial_release_pipeline_dry_run_does_not_persist_changes(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        add_quality_blocked_candidate(session)
        service = build_release_service(session, tmp_path)

        result = service.run(reference_date=REFERENCE_DATE, dry_run=True)

        assert result.autoapproved_count == 4
        assert result.dispatched_count == 4
        assert result.export_base_total_items == 4
        assert result.legacy_export_json_count == 0
        assert result.legacy_export_blocked_series_count == 0
        assert session.get(ContentCandidate, 101).status == "draft"
        assert session.get(ContentCandidate, 101).autoapproved is None
        assert session.get(ContentCandidate, 106).status == "draft"
        assert session.get(ContentCandidate, 109).status == "draft"
        assert session.get(ContentCandidate, 105).quality_check_passed is None
        assert not (tmp_path / "exports" / "export_base.json").exists()
        assert not (tmp_path / "export" / "legacy_export.json").exists()
    finally:
        session.close()


def test_editorial_release_pipeline_keeps_sensitive_narratives_manual_in_v1(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        add_critical_narrative_candidates(session)
        service = build_release_service(session, tmp_path)

        result = service.run(reference_date=REFERENCE_DATE, dry_run=False)
        session.commit()

        assert result.autoapprovable_count == 4
        assert result.autoapproved_count == 4
        assert result.dispatched_count == 4
        assert result.export_base_total_items == 4
        assert result.legacy_export_json_count == 0
        assert result.legacy_export_blocked_series_count == 0
        assert session.get(ContentCandidate, 107).status == "draft"
        assert session.get(ContentCandidate, 108).status == "draft"
        assert session.get(ContentCandidate, 103).status == "published"
        assert session.get(ContentCandidate, 106).status == "published"
        assert session.get(ContentCandidate, 102).status == "published"
        assert session.get(ContentCandidate, 109).status == "published"
    finally:
        session.close()


def test_editorial_release_pipeline_dispatches_future_preview_before_kickoff(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        add_future_preview_candidate(session)
        service = build_release_service(session, tmp_path)

        result = service.run(reference_date=REFERENCE_DATE, dry_run=False)
        session.commit()

        assert result.autoapproved_count == 5
        assert result.dispatched_count == 5
        assert result.export_base_total_items == 4
        assert session.get(ContentCandidate, 110).status == "published"
        assert session.get(ContentCandidate, 110).published_at is not None
        assert session.get(ContentCandidate, 110).autoapproved is True
    finally:
        session.close()


def test_editorial_release_pipeline_dispatches_ready_approved_candidates_from_previous_runs(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        add_ready_approved_preview_candidate(session)
        service = build_release_service(session, tmp_path)

        result = service.run(reference_date=REFERENCE_DATE, dry_run=False)
        session.commit()

        export_path = tmp_path / "exports" / "export_base.json"
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        exported_ids = {
            item["id"]
            for items in payload["competitions"]["tercera_rfef_g11"].values()
            for item in items
        }

        assert result.autoapproved_count == 4
        assert result.dispatched_count == 5
        assert result.export_base_total_items == 5
        assert session.get(ContentCandidate, 111).status == "published"
        assert session.get(ContentCandidate, 111).published_at is not None
        assert 111 in exported_ids
    finally:
        session.close()


def test_editorial_release_pipeline_can_generate_legacy_export_when_enabled(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        add_quality_blocked_candidate(session)
        service = build_release_service_with_legacy_export(session, tmp_path)

        result = service.run(reference_date=REFERENCE_DATE, dry_run=False)
        session.commit()

        legacy_path = tmp_path / "export" / "legacy_export.json"
        payload = json.loads(legacy_path.read_text(encoding="utf-8"))

        assert result.export_base_total_items == 4
        assert result.legacy_export_json_count == 4
        assert result.legacy_export_blocked_series_count == 0
        assert result.legacy_export_json_path == str(legacy_path)
        assert {row["id"] for row in payload} == {102, 103, 106, 109}
    finally:
        session.close()


def test_editorial_release_pipeline_publish_flags_use_browser_service_once(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        x_publication_service = Mock()
        x_browser_publication_service = Mock()
        x_browser_publication_service.publish_selected_pending.return_value = XBrowserBatchResult(
            dry_run=False,
            published_count=2,
            error_count=0,
            skipped_count=0,
        )
        x_browser_publication_service.build_views_from_batch_result.return_value = []
        service = EditorialReleasePipelineService(
            session,
            settings=build_settings(app_root=tmp_path),
            x_publication_service=x_publication_service,
            x_browser_publication_service=x_browser_publication_service,
        )

        result = service.run(
            reference_date=REFERENCE_DATE,
            dry_run=False,
            publish_to_x=True,
            publish_via_browser=True,
        )
        session.commit()

        assert result.dispatched_count == 2
        assert result.x_publish_enabled is True
        assert result.x_published_count == 2
        x_publication_service.publish_candidates.assert_not_called()
        x_browser_publication_service.publish_selected_pending.assert_called_once_with(
            [102, 109],
            limit=2,
            dry_run=False,
            bypass_schedule=False,
        )
        x_browser_publication_service.build_views_from_batch_result.assert_called_once()
    finally:
        session.close()


def test_browser_release_caps_dispatch_after_wide_autoapproval_pool(tmp_path: Path) -> None:
    session = build_session()
    try:
        valid_ids = seed_wednesday_browser_backlog(session)
        x_browser_publication_service = Mock()
        x_browser_publication_service.publish_selected_pending.return_value = XBrowserBatchResult(
            dry_run=False,
            published_count=4,
            error_count=0,
            skipped_count=0,
        )
        x_browser_publication_service.build_views_from_batch_result.return_value = []
        service = EditorialReleasePipelineService(
            session,
            settings=build_settings(app_root=tmp_path),
            x_browser_publication_service=x_browser_publication_service,
        )

        result = service.run(
            reference_date=WEDNESDAY_REFERENCE_DATE,
            dry_run=False,
            publish_via_browser=True,
            publish_limit=4,
        )
        session.commit()

        selected_ids = set(valid_ids[:4])
        deferred_ids = set(valid_ids[4:])
        assert result.drafts_found == 53
        assert result.autoapprovable_count == 47
        assert result.autoapproved_count == 47
        assert result.dispatched_count == 4
        assert {row.id for row in result.dispatched_rows} == selected_ids
        assert {session.get(ContentCandidate, candidate_id).status for candidate_id in selected_ids} == {"published"}
        assert {session.get(ContentCandidate, candidate_id).status for candidate_id in deferred_ids} == {"approved"}
        assert {session.get(ContentCandidate, 1900 + index).status for index in range(6)} == {"draft"}
        assert {session.get(ContentCandidate, 1900 + index).quality_check_passed for index in range(6)} == {False}
        x_browser_publication_service.publish_selected_pending.assert_called_once_with(
            valid_ids[:4],
            limit=4,
            dry_run=False,
            bypass_schedule=False,
        )
    finally:
        session.close()


def test_browser_release_deferred_approved_candidates_do_not_enter_browser_pending_queue(tmp_path: Path) -> None:
    session = build_session()
    try:
        valid_ids = seed_wednesday_browser_backlog(session)
        x_browser_publication_service = Mock()
        x_browser_publication_service.publish_selected_pending.return_value = XBrowserBatchResult(
            dry_run=False,
            published_count=0,
            error_count=0,
            skipped_count=0,
        )
        x_browser_publication_service.build_views_from_batch_result.return_value = []
        settings = build_settings(app_root=tmp_path)
        service = EditorialReleasePipelineService(
            session,
            settings=settings,
            x_browser_publication_service=x_browser_publication_service,
        )

        result = service.run(
            reference_date=WEDNESDAY_REFERENCE_DATE,
            dry_run=False,
            publish_via_browser=True,
            publish_limit=4,
        )
        session.commit()

        scheduler = XPublicationScheduler(
            settings=settings,
            now_provider=lambda: datetime(2026, 3, 18, 20, 30, tzinfo=ZoneInfo("Europe/Madrid")),
        )
        browser_service = XBrowserPublicationService(
            session,
            settings=settings,
            scheduler=scheduler,
            publisher=Mock(),
        )

        assert result.dispatched_count == 4
        assert {row.id for row in browser_service.list_pending(limit=100)} == set(valid_ids[:4])
        assert all(session.get(ContentCandidate, candidate_id).status == "approved" for candidate_id in valid_ids[4:])
    finally:
        session.close()


def test_editorial_release_pipeline_caps_browser_publish_by_run_limit(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_release_candidates(session)
        x_browser_publication_service = Mock()
        x_browser_publication_service.publish_selected_pending.return_value = XBrowserBatchResult(
            dry_run=False,
            published_count=0,
            error_count=0,
            skipped_count=0,
        )
        x_browser_publication_service.build_views_from_batch_result.return_value = []
        service = EditorialReleasePipelineService(
            session,
            settings=build_settings(app_root=tmp_path),
            x_browser_publication_service=x_browser_publication_service,
        )

        result = service.run(
            reference_date=REFERENCE_DATE,
            limit=2,
            dry_run=False,
            publish_via_browser=True,
        )
        session.commit()

        assert result.x_published_count == 0
        x_browser_publication_service.publish_selected_pending.assert_called_once_with(
            [],
            limit=2,
            dry_run=False,
            bypass_schedule=False,
        )
    finally:
        session.close()
