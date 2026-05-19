from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from app.db.models import ContentCandidate
from app.services.editorial_approval_policy import (
    FRIDAY_AUTOAPPROVABLE_CONTENT_TYPES,
    MONDAY_AUTOAPPROVABLE_CONTENT_TYPES,
    THURSDAY_AUTOAPPROVABLE_CONTENT_TYPES,
    EditorialApprovalPolicyService,
)
from tests.unit.services.service_test_support import build_session, build_settings
from tests.unit.services.test_editorial_narratives import seed_competition


def test_autoapprove_includes_logical_reference_date_even_if_created_next_day() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Baleares",
            teams=["CD Llosetense", "SD Portmany"],
            standings_rows=[],
            match_rows=[
                {
                    "round_name": "Jornada 26",
                    "match_date": date(2026, 3, 16),
                    "match_time": datetime(2026, 3, 16, 10, 0, tzinfo=UTC).time(),
                    "home_team": "CD Llosetense",
                    "away_team": "SD Portmany",
                    "home_score": 2,
                    "away_score": 0,
                }
            ],
        )
        session.add(
            ContentCandidate(
                id=901,
                competition_slug="tercera_rfef_g11",
                content_type="results_roundup",
                priority=90,
                text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 26",
                payload_json={
                    "reference_date": "2026-03-17",
                    "competition_name": "3a RFEF Baleares",
                    "content_key": "results_roundup:j26:test",
                    "source_payload": {
                        "reference_date": "2026-03-17",
                        "selected_matches_count": 1,
                        "omitted_matches_count": 0,
                        "group_label": "Jornada 26",
                        "matches": [
                            {
                                "round_name": "Jornada 26",
                                "match_date": "2026-03-16",
                                "home_team": "CD Llosetense",
                                "away_team": "SD Portmany",
                                "home_score": 2,
                                "away_score": 0,
                            }
                        ],
                    },
                },
                source_summary_hash="approval-backfill-901",
                scheduled_at=None,
                status="draft",
                created_at=datetime(2026, 3, 17, 8, 30, tzinfo=UTC),
                updated_at=datetime(2026, 3, 17, 8, 30, tzinfo=UTC),
            )
        )
        session.commit()

        result = EditorialApprovalPolicyService(session, settings=build_settings()).autoapprove(
            reference_date=date(2026, 3, 17),
            dry_run=True,
        )

        rows = {row.id: row for row in result.rows}
        assert result.drafts_found == 1
        assert rows[901].autoapprovable is True
        assert rows[901].policy_reason == "policy_autoapprove_safe_type"
    finally:
        session.close()


def test_autoapprove_includes_old_drafts_when_they_enter_release_window() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Baleares",
            teams=["CD Llosetense", "SD Portmany"],
            standings_rows=[],
            match_rows=[
                {
                    "round_name": "Jornada 26",
                    "match_date": date(2026, 3, 16),
                    "match_time": datetime(2026, 3, 16, 10, 0, tzinfo=UTC).time(),
                    "home_team": "CD Llosetense",
                    "away_team": "SD Portmany",
                    "home_score": 2,
                    "away_score": 0,
                }
            ],
        )
        session.add(
            ContentCandidate(
                id=902,
                competition_slug="tercera_rfef_g11",
                content_type="results_roundup",
                priority=90,
                text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 26",
                payload_json={
                    "reference_date": "2026-03-10",
                    "competition_name": "3a RFEF Baleares",
                    "content_key": "results_roundup:j26:older-draft",
                    "source_payload": {
                        "reference_date": "2026-03-10",
                        "selected_matches_count": 1,
                        "omitted_matches_count": 0,
                        "group_label": "Jornada 26",
                        "matches": [
                            {
                                "round_name": "Jornada 26",
                                "match_date": "2026-03-16",
                                "home_team": "CD Llosetense",
                                "away_team": "SD Portmany",
                                "home_score": 2,
                                "away_score": 0,
                            }
                        ],
                    },
                },
                source_summary_hash="approval-backfill-902",
                scheduled_at=None,
                status="draft",
                created_at=datetime(2026, 3, 10, 8, 30, tzinfo=UTC),
                updated_at=datetime(2026, 3, 10, 8, 30, tzinfo=UTC),
            )
        )
        session.commit()

        result = EditorialApprovalPolicyService(session, settings=build_settings()).autoapprove(
            reference_date=date(2026, 3, 17),
            dry_run=True,
        )

        rows = {row.id: row for row in result.rows}
        assert result.drafts_found == 1
        assert rows[902].autoapprovable is True
        assert rows[902].policy_reason == "policy_autoapprove_safe_type"
    finally:
        session.close()


def test_monday_autoapproves_top_scorer_update_when_configured() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Baleares",
            teams=["CD Manacor", "CE Mercadal"],
            standings_rows=[],
            match_rows=[],
        )
        session.add(
            ContentCandidate(
                id=903,
                competition_slug="tercera_rfef_g11",
                content_type="top_scorer_update",
                priority=75,
                text_draft="Pichichi provisional en 3a RFEF Baleares: Joan Serra (CD Manacor) manda con 8 goles.",
                payload_json={
                    "reference_date": "2026-03-16",
                    "competition_name": "3a RFEF Baleares",
                    "content_key": "top_scorer_update:tercera_rfef_g11:2025-26",
                    "source_payload": {
                        "leader": {"player": "Joan Serra", "team": "CD Manacor", "goals": 8},
                        "rows": [{"player": "Joan Serra", "team": "CD Manacor", "goals": 8}],
                        "leader_goals": 8,
                        "teams": ["CD Manacor"],
                        "season": "2025-26",
                    },
                },
                source_summary_hash="approval-top-scorer-903",
                status="draft",
                created_at=datetime(2026, 3, 16, 8, 30, tzinfo=UTC),
                updated_at=datetime(2026, 3, 16, 8, 30, tzinfo=UTC),
            )
        )
        session.commit()

        service = EditorialApprovalPolicyService(session, settings=build_settings())
        service.quality_service = Mock()
        service.quality_service.check_candidates.return_value = SimpleNamespace(
            rows=[SimpleNamespace(id=903, passed=True, errors=[])]
        )

        result = service.autoapprove(reference_date=date(2026, 3, 16), dry_run=True)

        rows = {row.id: row for row in result.rows}
        assert (rows[903].content_type,) == MONDAY_AUTOAPPROVABLE_CONTENT_TYPES
        assert rows[903].autoapprovable is True
        assert rows[903].policy_reason == "policy_autoapprove_safe_type"
    finally:
        session.close()


def test_thursday_autoapproves_top_scorer_update_when_configured() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Baleares",
            teams=["CD Manacor", "CE Mercadal"],
            standings_rows=[],
            match_rows=[],
        )
        session.add(
            ContentCandidate(
                id=904,
                competition_slug="tercera_rfef_g11",
                content_type="top_scorer_update",
                priority=75,
                text_draft="Pichichi provisional en 3a RFEF Baleares: Joan Serra (CD Manacor) manda con 8 goles.",
                payload_json={
                    "reference_date": "2026-03-19",
                    "competition_name": "3a RFEF Baleares",
                    "content_key": "top_scorer_update:tercera_rfef_g11:2025-26",
                    "source_payload": {
                        "leader": {"player": "Joan Serra", "team": "CD Manacor", "goals": 8},
                        "rows": [{"player": "Joan Serra", "team": "CD Manacor", "goals": 8}],
                        "leader_goals": 8,
                        "teams": ["CD Manacor"],
                        "season": "2025-26",
                    },
                },
                source_summary_hash="approval-top-scorer-904",
                status="draft",
                created_at=datetime(2026, 3, 19, 8, 30, tzinfo=UTC),
                updated_at=datetime(2026, 3, 19, 8, 30, tzinfo=UTC),
            )
        )
        session.commit()

        service = EditorialApprovalPolicyService(session, settings=build_settings())
        service.quality_service = Mock()
        service.quality_service.check_candidates.return_value = SimpleNamespace(
            rows=[SimpleNamespace(id=904, passed=True, errors=[])]
        )

        result = service.autoapprove(reference_date=date(2026, 3, 19), dry_run=True)

        rows = {row.id: row for row in result.rows}
        assert rows[904].content_type in THURSDAY_AUTOAPPROVABLE_CONTENT_TYPES
        assert rows[904].autoapprovable is True
        assert rows[904].policy_reason == "policy_autoapprove_safe_type"
    finally:
        session.close()


def test_monday_autoapproves_strongest_race_narrative_per_competition_and_keeps_milestone_manual() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Baleares",
            teams=["CD Manacor", "CE Mercadal", "SD Portmany", "RCD Mallorca B"],
            standings_rows=[],
            match_rows=[],
        )
        session.add_all(
            [
                ContentCandidate(
                    id=907,
                    competition_slug="tercera_rfef_g11",
                    content_type="race_narrative",
                    priority=87,
                    text_draft="CD Manacor y CE Mercadal sostienen un pulso directo por el liderato con solo un punto de margen.",
                    payload_json={
                        "reference_date": "2026-03-16",
                        "content_key": "race_narrative:title_race:tercera_rfef_g11:1:manacor-mercadal",
                        "source_payload": {
                            "narrative_type": "title_race",
                            "target_label": "liderato",
                            "target_position": 1,
                            "team_count": 2,
                            "points_span": 1,
                            "rounds_remaining": 4,
                            "teams": [
                                {"team": "CD Manacor", "position": 1, "points": 58, "gap_to_target": 0},
                                {"team": "CE Mercadal", "position": 2, "points": 57, "gap_to_target": 1},
                            ],
                        },
                    },
                    source_summary_hash="approval-race-907",
                    status="draft",
                    created_at=datetime(2026, 3, 16, 8, 30, tzinfo=UTC),
                    updated_at=datetime(2026, 3, 16, 8, 30, tzinfo=UTC),
                ),
                ContentCandidate(
                    id=908,
                    competition_slug="tercera_rfef_g11",
                    content_type="race_narrative",
                    priority=83,
                    text_draft="SD Portmany, CE Mercadal y RCD Mallorca B siguen apretando por la ultima plaza de playoff.",
                    payload_json={
                        "reference_date": "2026-03-16",
                        "content_key": "race_narrative:playoff_race:tercera_rfef_g11:4:portmany-mercadal-mallorca-b",
                        "source_payload": {
                            "narrative_type": "playoff_race",
                            "target_label": "4a plaza de playoff",
                            "target_position": 4,
                            "team_count": 3,
                            "points_span": 1,
                            "rounds_remaining": 4,
                            "teams": [
                                {"team": "SD Portmany", "position": 4, "points": 49, "gap_to_target": 0},
                                {"team": "CE Mercadal", "position": 5, "points": 49, "gap_to_target": 0},
                                {"team": "RCD Mallorca B", "position": 6, "points": 48, "gap_to_target": 1},
                            ],
                        },
                    },
                    source_summary_hash="approval-race-908",
                    status="draft",
                    created_at=datetime(2026, 3, 16, 8, 31, tzinfo=UTC),
                    updated_at=datetime(2026, 3, 16, 8, 31, tzinfo=UTC),
                ),
                ContentCandidate(
                    id=909,
                    competition_slug="tercera_rfef_g11",
                    content_type="milestone_story",
                    priority=81,
                    text_draft="CD Manacor alcanza un nuevo hito ofensivo, pero esta pieza sigue en revision manual.",
                    payload_json={
                        "reference_date": "2026-03-16",
                        "content_key": "milestone_story:top_scoring_team:manacor",
                        "source_payload": {
                            "milestone_type": "top_scoring_team",
                            "team": "CD Manacor",
                            "teams": ["CD Manacor"],
                            "goals_for": 42,
                            "leader_margin": 3,
                        },
                    },
                    source_summary_hash="approval-milestone-909",
                    status="draft",
                    created_at=datetime(2026, 3, 16, 8, 32, tzinfo=UTC),
                    updated_at=datetime(2026, 3, 16, 8, 32, tzinfo=UTC),
                ),
            ]
        )
        session.commit()

        service = EditorialApprovalPolicyService(session, settings=build_settings())
        service.quality_service = Mock()
        service.quality_service.check_candidates.return_value = SimpleNamespace(
            rows=[
                SimpleNamespace(id=907, passed=True, errors=[]),
                SimpleNamespace(id=908, passed=True, errors=[]),
            ]
        )

        result = service.autoapprove(reference_date=date(2026, 3, 16), dry_run=True)
        rows = {row.id: row for row in result.rows}

        assert rows[907].autoapprovable is True
        assert rows[907].policy_reason == "policy_autoapprove_race_narrative"
        assert rows[908].autoapprovable is False
        assert rows[908].policy_reason == "race_narrative_competition_limit"
        assert rows[909].autoapprovable is False
        assert rows[909].policy_reason == "manual_review_policy"
    finally:
        session.close()


def test_race_narrative_stays_manual_outside_monday_even_when_quality_passes() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Baleares",
            teams=["CD Manacor", "CE Mercadal"],
            standings_rows=[],
            match_rows=[],
        )
        session.add(
            ContentCandidate(
                id=910,
                competition_slug="tercera_rfef_g11",
                content_type="race_narrative",
                priority=87,
                text_draft="CD Manacor y CE Mercadal siguen en un margen minimo por el liderato.",
                payload_json={
                    "reference_date": "2026-03-20",
                    "content_key": "race_narrative:title_race:tercera_rfef_g11:1:manacor-mercadal:friday",
                    "source_payload": {
                        "narrative_type": "title_race",
                        "target_label": "liderato",
                        "target_position": 1,
                        "team_count": 2,
                        "points_span": 1,
                        "rounds_remaining": 4,
                        "teams": [
                            {"team": "CD Manacor", "position": 1, "points": 58, "gap_to_target": 0},
                            {"team": "CE Mercadal", "position": 2, "points": 57, "gap_to_target": 1},
                        ],
                    },
                },
                source_summary_hash="approval-race-910",
                status="draft",
                created_at=datetime(2026, 3, 20, 8, 30, tzinfo=UTC),
                updated_at=datetime(2026, 3, 20, 8, 30, tzinfo=UTC),
            )
        )
        session.commit()

        service = EditorialApprovalPolicyService(session, settings=build_settings())
        service.quality_service = Mock()
        service.quality_service.check_candidates.return_value = SimpleNamespace(
            rows=[SimpleNamespace(id=910, passed=True, errors=[])]
        )

        result = service.autoapprove(reference_date=date(2026, 3, 20), dry_run=True)
        rows = {row.id: row for row in result.rows}

        assert rows[910].autoapprovable is False
        assert rows[910].policy_reason == "race_narrative_day_not_enabled"
    finally:
        session.close()


def test_quality_precheck_excludes_race_narrative_outside_monday() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Baleares",
            teams=["CD Manacor", "CE Mercadal"],
            standings_rows=[],
            match_rows=[],
        )
        session.add(
            ContentCandidate(
                id=911,
                competition_slug="tercera_rfef_g11",
                content_type="race_narrative",
                priority=87,
                text_draft="CD Manacor y CE Mercadal siguen en un margen minimo por el liderato.",
                payload_json={
                    "reference_date": "2026-03-20",
                    "content_key": "race_narrative:title_race:tercera_rfef_g11:1:manacor-mercadal:precheck-friday",
                    "source_payload": {
                        "narrative_type": "title_race",
                        "target_label": "liderato",
                        "target_position": 1,
                        "team_count": 2,
                        "points_span": 1,
                        "rounds_remaining": 4,
                        "teams": [
                            {"team": "CD Manacor", "position": 1, "points": 58, "gap_to_target": 0},
                            {"team": "CE Mercadal", "position": 2, "points": 57, "gap_to_target": 1},
                        ],
                    },
                },
                source_summary_hash="approval-race-911",
                status="draft",
                created_at=datetime(2026, 3, 20, 8, 30, tzinfo=UTC),
                updated_at=datetime(2026, 3, 20, 8, 30, tzinfo=UTC),
            )
        )
        session.commit()

        service = EditorialApprovalPolicyService(session, settings=build_settings())

        result = service.candidate_ids_for_quality_precheck(reference_date=date(2026, 3, 20))

        assert result == []
    finally:
        session.close()


def test_friday_autoapproves_preview_and_match_impact_and_keeps_race_manual() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Baleares",
            teams=["CD Manacor", "CE Mercadal"],
            standings_rows=[],
            match_rows=[],
        )
        session.add_all(
            [
                ContentCandidate(
                    id=904,
                    competition_slug="tercera_rfef_g11",
                    content_type="featured_match_preview",
                    priority=80,
                    text_draft="PREVIA | 3a RFEF Baleares | CD Manacor vs CE Mercadal",
                    payload_json={"reference_date": "2026-03-20", "source_payload": {}},
                    source_summary_hash="approval-preview-904",
                    status="draft",
                    created_at=datetime(2026, 3, 20, 8, 30, tzinfo=UTC),
                    updated_at=datetime(2026, 3, 20, 8, 30, tzinfo=UTC),
                ),
                ContentCandidate(
                    id=905,
                    competition_slug="tercera_rfef_g11",
                    content_type="match_impact_scenario",
                    priority=79,
                    text_draft="Si gana el CD Manacor, entra en playoff.",
                    payload_json={"reference_date": "2026-03-20", "source_payload": {}},
                    source_summary_hash="approval-impact-905",
                    status="draft",
                    created_at=datetime(2026, 3, 20, 8, 31, tzinfo=UTC),
                    updated_at=datetime(2026, 3, 20, 8, 31, tzinfo=UTC),
                ),
                ContentCandidate(
                    id=906,
                    competition_slug="tercera_rfef_g11",
                    content_type="race_narrative",
                    priority=78,
                    text_draft="Tres equipos pelean por la ultima plaza de playoff.",
                    payload_json={"reference_date": "2026-03-20", "source_payload": {}},
                    source_summary_hash="approval-race-906",
                    status="draft",
                    created_at=datetime(2026, 3, 20, 8, 32, tzinfo=UTC),
                    updated_at=datetime(2026, 3, 20, 8, 32, tzinfo=UTC),
                ),
            ]
        )
        session.commit()

        service = EditorialApprovalPolicyService(session, settings=build_settings())
        service.quality_service = Mock()
        service.quality_service.check_candidates.return_value = SimpleNamespace(
            rows=[
                SimpleNamespace(id=904, passed=True, errors=[]),
                SimpleNamespace(id=905, passed=True, errors=[]),
            ]
        )

        result = service.autoapprove(reference_date=date(2026, 3, 20), dry_run=True)
        rows = {row.id: row for row in result.rows}

        assert set(FRIDAY_AUTOAPPROVABLE_CONTENT_TYPES) == {
            rows[904].content_type,
            rows[905].content_type,
        }
        assert rows[904].autoapprovable is True
        assert rows[905].autoapprovable is True
        assert rows[906].autoapprovable is False
        assert rows[906].policy_reason == "race_narrative_day_not_enabled"
    finally:
        session.close()
