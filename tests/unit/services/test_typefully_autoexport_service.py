from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import re
from unittest.mock import Mock

from typer.testing import CliRunner

from app.core.enums import ContentCandidateStatus
from app.pipelines import typefully_autoexport as typefully_autoexport_pipeline
from app.channels.typefully.client import TypefullyApiError
from app.channels.typefully.schemas import TypefullyDraftResponse
from app.core.enums import ContentType
from sqlalchemy import select

from app.db.models import Competition, ContentCandidate, Standing, Team
from app.schemas.typefully_autoexport import (
    TypefullyAutoexportCandidateView,
    TypefullyAutoexportLastRun,
    TypefullyAutoexportPhasePolicy,
    TypefullyAutoexportPolicy,
    TypefullyAutoexportStatusView,
)
from app.schemas.story_importance import StoryImportanceCandidateView
from app.services.typefully_autoexport_service import TypefullyAutoexportService
from tests.unit.services.test_editorial_narratives import seed_competition
from tests.unit.services.test_typefully_export_service import build_session, build_settings, seed_candidates


_ROUNDUP_SCORE_RE = re.compile(r"^(?P<home>.+?) (?P<home_score>\d+)-(?P<away_score>\d+) (?P<away>.+)$")


def _roundup_payload_from_text(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return {
            "group_label": "Jornada 27",
            "selected_matches_count": 0,
            "omitted_matches_count": 0,
            "matches": [],
        }
    header_parts = [part.strip() for part in lines[0].split("|")]
    group_label = header_parts[2] if len(header_parts) >= 3 else "Jornada 27"
    matches: list[dict[str, int | str]] = []
    for line in lines[1:]:
        match = _ROUNDUP_SCORE_RE.match(line)
        if match is None:
            continue
        matches.append(
            {
                "home_team": match.group("home"),
                "away_team": match.group("away"),
                "home_score": int(match.group("home_score")),
                "away_score": int(match.group("away_score")),
            }
        )
    return {
        "group_label": group_label,
        "selected_matches_count": len(matches),
        "omitted_matches_count": 0,
        "matches": matches,
    }


def seed_manual_only_candidates(session) -> None:
    now = datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc)
    session.add_all(
        [
            ContentCandidate(
                id=17,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="viral_story",
                priority=72,
                text_draft="Historia viral controlada",
                rewritten_text=None,
                rewrite_status=None,
                rewrite_model=None,
                rewrite_timestamp=None,
                rewrite_error=None,
                payload_json={},
                source_summary_hash="hash-17",
                scheduled_at=None,
                status="published",
                reviewed_at=now,
                approved_at=now,
                published_at=now,
                rejection_reason=None,
                external_publication_ref=None,
                external_channel=None,
                external_exported_at=None,
                external_publication_timestamp=None,
                external_publication_attempted_at=None,
                external_publication_error=None,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=18,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="metric_narrative",
                priority=66,
                text_draft="Narrativa metrica",
                rewritten_text=None,
                rewrite_status=None,
                rewrite_model=None,
                rewrite_timestamp=None,
                rewrite_error=None,
                payload_json={},
                source_summary_hash="hash-18",
                scheduled_at=None,
                status="published",
                reviewed_at=now,
                approved_at=now,
                published_at=now,
                rejection_reason=None,
                external_publication_ref=None,
                external_channel=None,
                external_exported_at=None,
                external_publication_timestamp=None,
                external_publication_attempted_at=None,
                external_publication_error=None,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()


def build_policy(enabled: bool = True, phase: int = 3) -> TypefullyAutoexportPolicy:
    return TypefullyAutoexportPolicy(
        enabled=enabled,
        phase=phase,
        default_limit=10,
        use_rewrite_by_default=True,
        max_text_length=280,
        duplicate_window_hours=72,
        max_line_breaks=6,
        max_exports_per_run=5,
        max_exports_per_day=None,
        stop_on_capacity_limit=True,
        capacity_error_codes=["MONETIZATION_ERROR"],
        allowed_content_types=[
            ContentType.RESULTS_ROUNDUP,
            ContentType.STANDINGS_ROUNDUP,
            ContentType.PREVIEW,
            ContentType.RANKING,
        ],
        manual_review_content_types=[
            ContentType.MATCH_RESULT,
            ContentType.STANDINGS,
            ContentType.FEATURED_MATCH_PREVIEW,
            ContentType.FEATURED_MATCH_EVENT,
            ContentType.STANDINGS_EVENT,
            ContentType.FORM_EVENT,
            ContentType.FORM_RANKING,
            ContentType.STAT_NARRATIVE,
            ContentType.METRIC_NARRATIVE,
            ContentType.VIRAL_STORY,
        ],
        validation_required_content_types=[],
        phases={
            1: TypefullyAutoexportPhasePolicy(
                allowed_content_types=[
                    ContentType.RESULTS_ROUNDUP,
                    ContentType.STANDINGS_ROUNDUP,
                    ContentType.PREVIEW,
                    ContentType.RANKING,
                ],
                validation_required_content_types=[],
            ),
            2: TypefullyAutoexportPhasePolicy(
                allowed_content_types=[
                    ContentType.RESULTS_ROUNDUP,
                    ContentType.STANDINGS_ROUNDUP,
                    ContentType.PREVIEW,
                    ContentType.RANKING,
                ],
                validation_required_content_types=[],
            ),
            3: TypefullyAutoexportPhasePolicy(
                allowed_content_types=[
                    ContentType.RESULTS_ROUNDUP,
                    ContentType.STANDINGS_ROUNDUP,
                    ContentType.PREVIEW,
                    ContentType.RANKING,
                ],
                validation_required_content_types=[],
            ),
        },
    )


def add_safe_candidate(session, candidate_id: int, text: str | None = None) -> None:
    now = datetime(2026, 3, 18, 10, 10, tzinfo=timezone.utc)
    session.add(
        ContentCandidate(
            id=candidate_id,
            competition_slug="segunda_rfef_g3_baleares",
            content_type="match_result",
            priority=90 - candidate_id,
            text_draft=text or f"RESULTADO FINAL Equipo {candidate_id} 1-0 Rival {candidate_id}",
            rewritten_text=None,
            rewrite_status=None,
            rewrite_model=None,
            rewrite_timestamp=None,
            rewrite_error=None,
            payload_json={},
            source_summary_hash=f"hash-{candidate_id}",
            scheduled_at=None,
            status="published",
            reviewed_at=now,
            approved_at=now,
            published_at=now,
            rejection_reason=None,
            external_publication_ref=None,
            external_channel=None,
            external_exported_at=None,
            external_publication_timestamp=None,
            external_publication_attempted_at=None,
            external_publication_error=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def add_results_roundup_candidate(
    session,
    candidate_id: int,
    text: str | None = None,
    *,
    priority: int = 95,
    created_at: datetime | None = None,
) -> None:
    competition = session.query(Competition).filter_by(code="segunda_rfef_g3_baleares").one_or_none()
    if competition is None:
        seed_competition(
            session,
            code="segunda_rfef_g3_baleares",
            name="2a RFEF Grupo 3",
            teams=["Torrent CF", "UE Porreres", "UE Sant Andreu", "Atletico Baleares", "UD Poblense"],
            standings_rows=[
                {"position": 1, "team": "UE Sant Andreu", "played": 27, "wins": 16, "draws": 6, "losses": 5, "goals_for": 40, "goals_against": 19, "goal_difference": 21, "points": 54},
                {"position": 2, "team": "Atletico Baleares", "played": 27, "wins": 14, "draws": 6, "losses": 7, "goals_for": 35, "goals_against": 20, "goal_difference": 15, "points": 48},
                {"position": 3, "team": "UD Poblense", "played": 27, "wins": 14, "draws": 6, "losses": 7, "goals_for": 34, "goals_against": 22, "goal_difference": 12, "points": 48},
                {"position": 4, "team": "Torrent CF", "played": 27, "wins": 10, "draws": 8, "losses": 9, "goals_for": 25, "goals_against": 23, "goal_difference": 2, "points": 38},
                {"position": 5, "team": "UE Porreres", "played": 27, "wins": 9, "draws": 8, "losses": 10, "goals_for": 22, "goals_against": 26, "goal_difference": -4, "points": 35},
            ],
            match_rows=[],
        )
    else:
        team_names = ["Torrent CF", "UE Porreres", "UE Sant Andreu", "Atletico Baleares", "UD Poblense"]
        team_map: dict[str, Team] = {}
        for team_name in team_names:
            normalized_name = f"segunda_rfef_g3_baleares-{team_name}".lower().replace(" ", "-")
            team = session.scalar(select(Team).where(Team.normalized_name == normalized_name))
            if team is None:
                team = Team(name=team_name, normalized_name=normalized_name, gender="male")
                session.add(team)
                session.flush()
            team_map[team_name] = team
        if not session.scalar(select(Standing.id).where(Standing.competition_id == competition.id)):
            scraped_at = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
            standings_rows = [
                {"position": 1, "team": "UE Sant Andreu", "played": 27, "wins": 16, "draws": 6, "losses": 5, "goals_for": 40, "goals_against": 19, "goal_difference": 21, "points": 54},
                {"position": 2, "team": "Atletico Baleares", "played": 27, "wins": 14, "draws": 6, "losses": 7, "goals_for": 35, "goals_against": 20, "goal_difference": 15, "points": 48},
                {"position": 3, "team": "UD Poblense", "played": 27, "wins": 14, "draws": 6, "losses": 7, "goals_for": 34, "goals_against": 22, "goal_difference": 12, "points": 48},
                {"position": 4, "team": "Torrent CF", "played": 27, "wins": 10, "draws": 8, "losses": 9, "goals_for": 25, "goals_against": 23, "goal_difference": 2, "points": 38},
                {"position": 5, "team": "UE Porreres", "played": 27, "wins": 9, "draws": 8, "losses": 10, "goals_for": 22, "goals_against": 26, "goal_difference": -4, "points": 35},
            ]
            for index, row in enumerate(standings_rows, start=1):
                session.add(
                    Standing(
                        source_name="futbolme",
                        source_url="https://example.com/segunda_rfef_g3_baleares/standings",
                        competition_id=competition.id,
                        season="2025-26",
                        group_name="Grupo test",
                        position=row["position"],
                        team_id=team_map[row["team"]].id,
                        team_raw=row["team"],
                        played=row["played"],
                        wins=row["wins"],
                        draws=row["draws"],
                        losses=row["losses"],
                        goals_for=row["goals_for"],
                        goals_against=row["goals_against"],
                        goal_difference=row["goal_difference"],
                        points=row["points"],
                        form_text=None,
                        scraped_at=scraped_at,
                        content_hash=f"segunda_rfef_g3_baleares-standing-{index}",
                        extra_data=None,
                    )
                )
            session.flush()
    now = created_at or datetime(2026, 3, 18, 10, 12 + (candidate_id % 10), tzinfo=timezone.utc)
    roundup_text = (
        text
        or "RESULTADOS | 2a RFEF con equipos baleares | Jornada 27\n\n"
        "Torrent CF 1-0 UE Porreres\n"
        "UE Sant Andreu 2-2 Atletico Baleares"
    )
    session.add(
        ContentCandidate(
            id=candidate_id,
            competition_slug="segunda_rfef_g3_baleares",
            content_type="results_roundup",
            priority=priority,
            text_draft=roundup_text,
            rewritten_text=None,
            rewrite_status=None,
            rewrite_model=None,
            rewrite_timestamp=None,
            rewrite_error=None,
            payload_json={
                "content_key": f"results_roundup:{candidate_id}",
                "source_payload": _roundup_payload_from_text(roundup_text),
            },
            source_summary_hash=f"hash-roundup-{candidate_id}",
            scheduled_at=None,
            status="published",
            reviewed_at=now,
            approved_at=now,
            published_at=now,
            rejection_reason=None,
            external_publication_ref=None,
            external_channel=None,
            external_exported_at=None,
            external_publication_timestamp=None,
            external_publication_attempted_at=None,
            external_publication_error=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def add_standings_roundup_candidate(
    session,
    candidate_id: int,
    text: str | None = None,
    *,
    priority: int = 83,
    created_at: datetime | None = None,
) -> None:
    competition = session.query(Competition).filter_by(code="segunda_rfef_g3_baleares").one_or_none()
    if competition is None:
        add_results_roundup_candidate(session, 9999)
        session.delete(session.get(ContentCandidate, 9999))
        session.commit()

    now = created_at or datetime(2026, 3, 18, 10, 30 + (candidate_id % 10), tzinfo=timezone.utc)
    roundup_text = (
        text
        or "CLASIFICACION | 2a RFEF con equipos baleares | Jornada 27\n\n"
        "1. UE Sant Andreu - 54 pts\n"
        "2. Atletico Baleares - 48 pts [PO]\n"
        "3. UD Poblense - 48 pts [PO]\n"
        "4. Torrent CF - 38 pts"
    )
    session.add(
        ContentCandidate(
            id=candidate_id,
            competition_slug="segunda_rfef_g3_baleares",
            content_type="standings_roundup",
            priority=priority,
            text_draft=roundup_text,
            rewritten_text=None,
            rewrite_status=None,
            rewrite_model=None,
            rewrite_timestamp=None,
            rewrite_error=None,
            payload_json={
                "content_key": f"standings_roundup:{candidate_id}",
                "source_payload": {
                    "group_label": "Jornada 27",
                    "selected_rows_count": 4,
                    "omitted_rows_count": 1,
                    "rows": [
                        {"position": 1, "team": "UE Sant Andreu", "points": 54},
                        {"position": 2, "team": "Atletico Baleares", "points": 48, "zone_tag": "playoff"},
                        {"position": 3, "team": "UD Poblense", "points": 48, "zone_tag": "playoff"},
                        {"position": 4, "team": "Torrent CF", "points": 38},
                    ],
                },
            },
            source_summary_hash=f"hash-standings-roundup-{candidate_id}",
            scheduled_at=None,
            status="published",
            reviewed_at=now,
            approved_at=now,
            published_at=now,
            rejection_reason=None,
            external_publication_ref=None,
            external_channel=None,
            external_exported_at=None,
            external_publication_timestamp=None,
            external_publication_attempted_at=None,
            external_publication_error=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def add_narrative_candidate(
    session,
    candidate_id: int,
    *,
    competition_slug: str = "segunda_rfef_g3_baleares",
    content_type: str,
    priority: int,
    text_draft: str,
    payload_json: dict,
    created_at: datetime | None = None,
) -> None:
    competition = session.query(Competition).filter_by(code=competition_slug).one_or_none()
    if competition is None:
        add_results_roundup_candidate(session, 9998)
        session.delete(session.get(ContentCandidate, 9998))
        session.commit()

    now = created_at or datetime(2026, 3, 18, 10, 40 + (candidate_id % 10), tzinfo=timezone.utc)
    session.add(
        ContentCandidate(
            id=candidate_id,
            competition_slug=competition_slug,
            content_type=content_type,
            priority=priority,
            text_draft=text_draft,
            rewritten_text=None,
            rewrite_status=None,
            rewrite_model=None,
            rewrite_timestamp=None,
            rewrite_error=None,
            payload_json=payload_json,
            source_summary_hash=f"hash-narrative-{candidate_id}",
            scheduled_at=None,
            status="published",
            reviewed_at=now,
            approved_at=now,
            published_at=now,
            rejection_reason=None,
            external_publication_ref=None,
            external_channel=None,
            external_exported_at=None,
            external_publication_timestamp=None,
            external_publication_attempted_at=None,
            external_publication_error=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_typefully_autoexport_dry_run_applies_policy() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        seed_manual_only_candidates(session)
        add_results_roundup_candidate(session, 9)
        add_standings_roundup_candidate(session, 10)
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True),
            settings=build_settings(),
        )

        result = service.run(dry_run=True, limit=10)

        assert result.phase == 3
        assert result.scanned_count == 8
        assert result.eligible_count == 3
        assert result.exported_count == 3
        assert result.blocked_count == 5
        assert result.capacity_deferred_count == 0
        rows = {row.id: row for row in result.rows}
        assert rows[9].importance_score is not None
        assert rows[10].importance_score is not None
        assert rows[6].importance_score is not None
        assert rows[9].importance_score > rows[6].importance_score
        assert rows[9].order_selected == 1
        assert rows[6].order_selected == 2
        assert rows[10].order_selected == 3
        assert {row.id for row in result.rows if row.autoexport_allowed} == {6, 9, 10}
        assert {row.id for row in result.rows if not row.autoexport_allowed} == {1, 5, 7, 17, 18}
    finally:
        session.close()


def test_typefully_autoexport_phase_1_blocks_non_safe_types() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        seed_manual_only_candidates(session)
        add_results_roundup_candidate(session, 9)
        add_standings_roundup_candidate(session, 10)
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1),
            settings=build_settings(),
        )

        rows = {row.id: row for row in service.list_candidates(limit=10)}

        assert rows[1].autoexport_allowed is False
        assert rows[1].policy_reason == "manual_review_policy"
        assert rows[6].autoexport_allowed is True
        assert rows[9].autoexport_allowed is True
        assert rows[10].autoexport_allowed is True
        assert rows[5].autoexport_allowed is False
        assert rows[5].policy_reason == "manual_review_policy"
        assert rows[17].autoexport_allowed is False
        assert rows[17].policy_reason == "manual_review_policy"
        assert rows[18].autoexport_allowed is False
        assert rows[18].policy_reason == "manual_review_policy"
    finally:
        session.close()


def test_typefully_autoexport_phase_1_keeps_narratives_manual() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        seed_manual_only_candidates(session)
        add_results_roundup_candidate(session, 9)
        add_narrative_candidate(
            session,
            11,
            content_type="featured_match_event",
            priority=96,
            text_draft="Pulso por el liderato entre UE Sant Andreu y Atletico Baleares.",
            payload_json={
                "content_key": "featured_match_event:sant-andreu-atletico",
                "source_payload": {
                    "home_team": "UE Sant Andreu",
                    "away_team": "Atletico Baleares",
                    "teams": ["UE Sant Andreu", "Atletico Baleares"],
                    "importance_score": 92,
                    "tags": ["title_race", "hot_form_match", "direct_rivalry"],
                    "home_recent_points": 13,
                    "away_recent_points": 11,
                },
            },
        )
        add_narrative_candidate(
            session,
            12,
            content_type="form_event",
            priority=82,
            text_draft="UE Porreres firma la mejor forma reciente en 2a RFEF con equipos baleares.",
            payload_json={
                "content_key": "form_event:best_form:porreres",
                "source_payload": {
                    "event_type": "best_form_team",
                    "team": "UE Porreres",
                    "teams": ["UE Porreres"],
                    "recent_points": 13,
                    "streak_length": 3,
                },
            },
        )
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1),
            settings=build_settings(),
        )

        result = service.run(dry_run=True, limit=20)
        rows = {row.id: row for row in result.rows}

        assert rows[11].autoexport_allowed is False
        assert rows[11].policy_reason == "manual_review_policy"
        assert rows[12].autoexport_allowed is False
        assert rows[12].policy_reason == "manual_review_policy"
        assert rows[18].autoexport_allowed is False
        assert rows[18].policy_reason == "manual_review_policy"
    finally:
        session.close()


def test_typefully_autoexport_blocks_narratives_by_policy_in_v1() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        add_results_roundup_candidate(session, 9)
        seed_competition(
            session,
            code="copa_test",
            name="Copa Test",
            teams=["UE Sant Andreu", "CD Alpha", "CD Beta"],
            standings_rows=[
                {"position": 1, "team": "UE Sant Andreu", "played": 4, "wins": 3, "draws": 1, "losses": 0, "goals_for": 9, "goals_against": 4, "goal_difference": 5, "points": 10},
                {"position": 2, "team": "CD Alpha", "played": 4, "wins": 3, "draws": 0, "losses": 1, "goals_for": 8, "goals_against": 5, "goal_difference": 3, "points": 9},
                {"position": 3, "team": "CD Beta", "played": 4, "wins": 2, "draws": 0, "losses": 2, "goals_for": 5, "goals_against": 6, "goal_difference": -1, "points": 6},
            ],
            match_rows=[],
        )
        add_narrative_candidate(
            session,
            21,
            content_type="featured_match_event",
            priority=96,
            text_draft="Pulso por el liderato entre UE Sant Andreu y Atletico Baleares.",
            payload_json={
                "content_key": "featured_match_event:sant-andreu-atletico",
                "source_payload": {
                    "home_team": "UE Sant Andreu",
                    "away_team": "Atletico Baleares",
                    "teams": ["UE Sant Andreu", "Atletico Baleares"],
                    "importance_score": 92,
                    "tags": ["title_race", "hot_form_match", "direct_rivalry"],
                    "home_recent_points": 13,
                    "away_recent_points": 11,
                },
            },
        )
        add_narrative_candidate(
            session,
            22,
            content_type="featured_match_event",
            priority=94,
            text_draft="Choque grande entre UE Sant Andreu y Atletico Baleares por la zona alta.",
            payload_json={
                "content_key": "featured_match_event:sant-andreu-atletico:secondary",
                "source_payload": {
                    "home_team": "UE Sant Andreu",
                    "away_team": "Atletico Baleares",
                    "teams": ["UE Sant Andreu", "Atletico Baleares"],
                    "importance_score": 92,
                    "tags": ["title_race", "hot_form_match", "direct_rivalry"],
                    "home_recent_points": 13,
                    "away_recent_points": 11,
                },
            },
        )
        add_narrative_candidate(
            session,
            23,
            competition_slug="copa_test",
            content_type="viral_story",
            priority=93,
            text_draft="UE Sant Andreu enlaza 5 victorias seguidas en Copa Test.",
            payload_json={
                "content_key": "viral:win_streak:sant-andreu-copa",
                "source_payload": {
                    "story_type": "win_streak",
                    "team": "UE Sant Andreu",
                    "teams": ["UE Sant Andreu"],
                    "metric_value": 5,
                    "streak_length": 5,
                },
            },
        )
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1),
            settings=build_settings(),
        )

        result = service.run(dry_run=True, limit=20)
        rows = {row.id: row for row in result.rows}

        assert rows[21].autoexport_allowed is False
        assert rows[21].policy_reason == "manual_review_policy"
        assert rows[22].autoexport_allowed is False
        assert rows[22].policy_reason == "manual_review_policy"
        assert rows[23].autoexport_allowed is False
        assert rows[23].policy_reason == "manual_review_policy"
    finally:
        session.close()


def test_typefully_autoexport_real_run_exports_only_allowed_types_and_persists() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        seed_manual_only_candidates(session)
        add_results_roundup_candidate(session, 9)
        add_standings_roundup_candidate(session, 10)
        publisher = Mock()
        publisher.export_text.side_effect = [
            TypefullyDraftResponse(
                draft_id="draft-9",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 18, 10, 5, tzinfo=timezone.utc),
                raw_response={"id": "draft-9"},
                dry_run=False,
            ),
            TypefullyDraftResponse(
                draft_id="draft-6",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 18, 10, 6, tzinfo=timezone.utc),
                raw_response={"id": "draft-6"},
                dry_run=False,
            ),
            TypefullyDraftResponse(
                draft_id="draft-10",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 18, 10, 7, tzinfo=timezone.utc),
                raw_response={"id": "draft-10"},
                dry_run=False,
            ),
        ]
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True),
            settings=build_settings(),
        )
        service.export_service.publisher = publisher

        result = service.run(dry_run=False, limit=10)
        session.commit()

        assert result.phase == 3
        assert result.eligible_count == 3
        assert result.exported_count == 3
        assert result.capacity_deferred_count == 0
        assert result.failed_count == 0
        assert result.rows[0].id == 9
        assert result.rows[0].order_selected == 1
        assert result.rows[1].id == 6
        assert result.rows[1].order_selected == 2
        assert result.rows[2].id == 10
        assert result.rows[2].order_selected == 3
        assert session.get(ContentCandidate, 1).external_publication_ref is None
        assert session.get(ContentCandidate, 6).external_publication_ref == "draft-6"
        assert session.get(ContentCandidate, 9).external_publication_ref == "draft-9"
        assert session.get(ContentCandidate, 10).external_publication_ref == "draft-10"
        assert session.get(ContentCandidate, 5).external_publication_ref is None
        assert session.get(ContentCandidate, 17).external_publication_ref is None
        assert session.get(ContentCandidate, 18).external_publication_ref is None
    finally:
        session.close()


def test_typefully_autoexport_filters_by_published_date() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        candidate = session.get(ContentCandidate, 6)
        assert candidate is not None
        candidate.published_at = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)
        session.add(candidate)
        session.commit()

        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True),
            settings=build_settings(timezone="Europe/Madrid"),
        )

        result = service.run(dry_run=True, reference_date=date(2026, 3, 15), limit=10)

        assert {row.id for row in result.rows} == {1, 5, 7}
    finally:
        session.close()


def test_typefully_autoexport_cli_status_reports_phase_and_last_run() -> None:
    runner = CliRunner()

    original_init_db = typefully_autoexport_pipeline.init_db
    original_session_scope = typefully_autoexport_pipeline.session_scope
    original_service = typefully_autoexport_pipeline.TypefullyAutoexportService
    try:
        class DummyService:
            def __init__(self, session) -> None:
                self.session = session

            def status(self) -> TypefullyAutoexportStatusView:
                return TypefullyAutoexportStatusView(
                    enabled=True,
                    phase=1,
                    importance_prioritization_enabled=True,
                    importance_tie_breaker="importance_score desc, priority desc, created_at asc, id asc",
                    max_exports_per_run=5,
                    max_exports_per_day=None,
                    stop_on_capacity_limit=True,
                    capacity_error_codes=["MONETIZATION_ERROR"],
                    allowed_content_types=[
                        ContentType.RESULTS_ROUNDUP,
                        ContentType.STANDINGS_ROUNDUP,
                        ContentType.PREVIEW,
                        ContentType.RANKING,
                    ],
                    validation_required_content_types=[],
                    manual_review_content_types=[
                        ContentType.MATCH_RESULT,
                        ContentType.STANDINGS,
                        ContentType.FEATURED_MATCH_PREVIEW,
                        ContentType.FEATURED_MATCH_EVENT,
                        ContentType.STANDINGS_EVENT,
                        ContentType.FORM_EVENT,
                        ContentType.FORM_RANKING,
                        ContentType.STAT_NARRATIVE,
                        ContentType.METRIC_NARRATIVE,
                        ContentType.VIRAL_STORY,
                    ],
                    pending_capacity_count=3,
                    pending_normal_count=4,
                    last_run=TypefullyAutoexportLastRun(
                        executed_at=datetime(2026, 3, 20, 10, 20, tzinfo=timezone.utc),
                        dry_run=False,
                        policy_enabled=True,
                        phase=1,
                        reference_date=date(2026, 3, 20),
                        scanned_count=12,
                        eligible_count=4,
                        exported_count=4,
                        blocked_count=2,
                        capacity_deferred_count=3,
                        failed_count=0,
                        capacity_limit_reached=True,
                        capacity_limit_reason="capacity_deferred:MONETIZATION_ERROR",
                    ),
                )

            def list_pending_capacity(self, **kwargs):
                return []

        @contextmanager
        def fake_session_scope():
            yield object()

        typefully_autoexport_pipeline.init_db = lambda: None
        typefully_autoexport_pipeline.session_scope = fake_session_scope
        typefully_autoexport_pipeline.TypefullyAutoexportService = DummyService

        result = runner.invoke(typefully_autoexport_pipeline.app, ["status"])

        assert result.exit_code == 0
        assert "enabled=true" in result.stdout
        assert "phase=1" in result.stdout
        assert "importance_prioritization_enabled=true" in result.stdout
        assert "importance_tie_breaker=importance_score desc, priority desc, created_at asc, id asc" in result.stdout
        assert "max_exports_per_run=5" in result.stdout
        assert "pending_capacity_count=3" in result.stdout
        assert "allowed_content_types=results_roundup, standings_roundup, preview, ranking" in result.stdout
        assert "last_execution=2026-03-20T10:20:00+00:00" in result.stdout
        assert "last_capacity_limit_reached=true" in result.stdout
        assert (
            "last_summary=AUTOEXPORT phase=1 scanned=12 eligible=4 exported=4 blocked=2 "
            "capacity_deferred=3 failed=0"
        ) in result.stdout
    finally:
        typefully_autoexport_pipeline.init_db = original_init_db
        typefully_autoexport_pipeline.session_scope = original_session_scope
        typefully_autoexport_pipeline.TypefullyAutoexportService = original_service


def test_typefully_autoexport_respects_max_exports_per_run() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        add_results_roundup_candidate(session, 9)
        add_results_roundup_candidate(
            session,
            10,
            text="RESULTADOS | 2a RFEF con equipos baleares | Jornada 28\n\nTorrent CF 2-1 UE Porreres\nUE Sant Andreu 1-0 Atletico Baleares",
        )
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1).model_copy(update={"max_exports_per_run": 2}),
            settings=build_settings(),
        )
        publisher = Mock()
        publisher.export_text.side_effect = [
            TypefullyDraftResponse(
                draft_id="draft-9",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 18, 10, 5, tzinfo=timezone.utc),
                raw_response={"id": "draft-9"},
                dry_run=False,
            ),
            TypefullyDraftResponse(
                draft_id="draft-10",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 18, 10, 6, tzinfo=timezone.utc),
                raw_response={"id": "draft-10"},
                dry_run=False,
            ),
        ]
        service.export_service.publisher = publisher

        result = service.run(dry_run=False, limit=10)
        session.commit()

        assert result.exported_count == 2
        assert result.capacity_deferred_count == 1
        assert result.failed_count == 0
        assert result.capacity_limit_reached is True
        assert session.get(ContentCandidate, 9).external_publication_ref is not None
        assert session.get(ContentCandidate, 10).external_publication_ref is not None
        assert session.get(ContentCandidate, 6).external_publication_error == "capacity_deferred:max_exports_per_run"
    finally:
        session.close()


def test_typefully_autoexport_scans_allowed_types_before_manual_backlog() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        seed_manual_only_candidates(session)
        add_results_roundup_candidate(session, 9, priority=99)
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1),
            settings=build_settings(),
        )

        result = service.run(dry_run=True, limit=1)

        assert result.scanned_count == 1
        assert len(result.rows) == 1
        assert result.rows[0].id == 9
        assert result.rows[0].content_type == ContentType.RESULTS_ROUNDUP
        assert result.rows[0].autoexport_allowed is True
    finally:
        session.close()


def test_typefully_autoexport_treats_monetization_error_as_capacity_limit() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        add_results_roundup_candidate(session, 9)
        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1).model_copy(update={"max_exports_per_run": 10}),
            settings=build_settings(),
        )
        publisher = Mock()
        publisher.export_text.side_effect = [
            TypefullyDraftResponse(
                draft_id="draft-9",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 18, 10, 5, tzinfo=timezone.utc),
                raw_response={"id": "draft-9"},
                dry_run=False,
            ),
            TypefullyApiError(
                "Typefully create draft failed with 402: {'code': 'MONETIZATION_ERROR'}",
                status_code=402,
                error_code="MONETIZATION_ERROR",
                detail="Please upgrade",
            ),
        ]
        service.export_service.publisher = publisher

        result = service.run(dry_run=False, limit=10)
        session.commit()

        assert result.exported_count == 1
        assert result.capacity_deferred_count == 1
        assert result.failed_count == 0
        assert result.capacity_limit_reason == "capacity_deferred:MONETIZATION_ERROR"
        assert session.get(ContentCandidate, 9).external_publication_ref is not None
        assert session.get(ContentCandidate, 6).external_publication_error == "capacity_deferred:MONETIZATION_ERROR"
    finally:
        session.close()


def test_typefully_autoexport_retries_capacity_deferred_candidates_later() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        add_results_roundup_candidate(session, 9)
        candidate = session.get(ContentCandidate, 9)
        assert candidate is not None
        candidate.external_publication_error = "capacity_deferred:MONETIZATION_ERROR"
        session.add(candidate)
        session.commit()

        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1),
            settings=build_settings(),
        )
        publisher = Mock()
        publisher.export_text.side_effect = [
            TypefullyDraftResponse(
                draft_id="draft-retry-1",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 19, 9, 0, tzinfo=timezone.utc),
                raw_response={"id": "draft-retry-1"},
                dry_run=False,
            ),
            TypefullyDraftResponse(
                draft_id="draft-retry-6",
                social_set_id="social-set-1",
                exported_at=datetime(2026, 3, 19, 9, 1, tzinfo=timezone.utc),
                raw_response={"id": "draft-retry-6"},
                dry_run=False,
            ),
        ]
        service.export_service.publisher = publisher

        result = service.run(dry_run=False, limit=10)
        session.commit()

        assert result.exported_count == 2
        assert result.capacity_deferred_count == 0
        assert session.get(ContentCandidate, 9).external_publication_ref == "draft-retry-1"
        assert session.get(ContentCandidate, 6).external_publication_ref == "draft-retry-6"
        assert session.get(ContentCandidate, 9).external_publication_error is None
    finally:
        session.close()


def test_typefully_autoexport_uses_stable_tiebreaker_on_same_importance() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        add_results_roundup_candidate(
            session,
            9,
            text="RESULTADOS | 2a RFEF con equipos baleares | Jornada 27\n\nTorrent CF 1-0 UE Porreres",
            priority=95,
            created_at=datetime(2026, 3, 18, 10, 20, tzinfo=timezone.utc),
        )
        add_results_roundup_candidate(
            session,
            10,
            text="RESULTADOS | 2a RFEF con equipos baleares | Jornada 28\n\nAtletico Baleares 1-0 UE Sant Andreu",
            priority=95,
            created_at=datetime(2026, 3, 18, 10, 25, tzinfo=timezone.utc),
        )
        class DummyStoryService:
            @staticmethod
            def score_row(row):
                return StoryImportanceCandidateView(
                    candidate_id=row.id,
                    competition_slug=row.competition_slug,
                    content_type=ContentType(row.content_type),
                    status=ContentCandidateStatus(row.status),
                    current_priority=row.priority,
                    importance_score=75,
                    importance_reasoning=["forced_tie"],
                    tags=["forced_tie"],
                    priority_bucket="medium",
                    excerpt=row.text_draft,
                    created_at=row.created_at,
                    published_at=row.published_at,
                )

            @staticmethod
            def is_automatic_narrative_content_type(content_type):
                return False

        service = TypefullyAutoexportService(
            session,
            policy=build_policy(enabled=True, phase=1),
            settings=build_settings(),
            story_service=DummyStoryService(),
        )

        result = service.run(dry_run=True, limit=10)

        ranked = [row for row in result.rows if row.autoexport_allowed and row.id in {9, 10}]
        assert ranked[0].importance_score == ranked[1].importance_score
        assert ranked[0].id == 9
        assert ranked[0].order_selected == 1
        assert ranked[1].id == 10
        assert ranked[1].order_selected == 2
    finally:
        session.close()


def test_typefully_autoexport_cli_pending_capacity_lists_deferred_rows() -> None:
    runner = CliRunner()

    original_init_db = typefully_autoexport_pipeline.init_db
    original_session_scope = typefully_autoexport_pipeline.session_scope
    original_service = typefully_autoexport_pipeline.TypefullyAutoexportService
    try:
        class DummyService:
            def __init__(self, session) -> None:
                self.session = session

            def status(self):
                raise AssertionError("status no debe llamarse en pending-capacity")

            def list_pending_capacity(self, **kwargs):
                return [
                    TypefullyAutoexportCandidateView(
                        id=42,
                        competition_slug="segunda_rfef_g3_baleares",
                        content_type=ContentType.RESULTS_ROUNDUP,
                    priority=97,
                    status=ContentCandidateStatus.PUBLISHED,
                    autoexport_allowed=True,
                    policy_reason="capacity_deferred:MONETIZATION_ERROR",
                    importance_score=79,
                    priority_bucket="medium",
                    order_selected=1,
                    quality_check_passed=True,
                    quality_check_errors=[],
                    export_outcome="capacity_deferred",
                        has_rewrite=False,
                        text_source="text_draft",
                        external_publication_ref=None,
                        external_publication_error="capacity_deferred:MONETIZATION_ERROR",
                        excerpt="RESULTADOS | 2a RFEF con equipos baleares | Jornada 27",
                    )
                ]

        @contextmanager
        def fake_session_scope():
            yield object()

        typefully_autoexport_pipeline.init_db = lambda: None
        typefully_autoexport_pipeline.session_scope = fake_session_scope
        typefully_autoexport_pipeline.TypefullyAutoexportService = DummyService

        result = runner.invoke(typefully_autoexport_pipeline.app, ["pending-capacity"])

        assert result.exit_code == 0
        assert "pending_capacity_count=1" in result.stdout
        assert "score=79" in result.stdout
        assert "bucket=medium" in result.stdout
        assert "order=1" in result.stdout
        assert "capacity_deferred:MONETIZATION_ERROR" in result.stdout
    finally:
        typefully_autoexport_pipeline.init_db = original_init_db
        typefully_autoexport_pipeline.session_scope = original_session_scope
        typefully_autoexport_pipeline.TypefullyAutoexportService = original_service
