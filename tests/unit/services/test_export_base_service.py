from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from pathlib import Path

from app.db.models import ContentCandidate, TeamMention
from app.services.export_base_service import ExportBaseService
from tests.unit.services.service_test_support import build_session, build_settings
from tests.unit.services.test_editorial_narratives import seed_competition


def seed_export_base_context(session) -> None:
    seed_competition(
        session,
        code="segunda_rfef_g3_baleares",
        name="2a RFEF Grupo 3",
        teams=["Atletico Baleares", "UD Poblense", "UE Porreres"],
        standings_rows=[
            {"position": 1, "team": "Atletico Baleares", "played": 27, "wins": 16, "draws": 7, "losses": 4, "goals_for": 39, "goals_against": 18, "goal_difference": 21, "points": 55},
            {"position": 2, "team": "UD Poblense", "played": 27, "wins": 15, "draws": 6, "losses": 6, "goals_for": 33, "goals_against": 20, "goal_difference": 13, "points": 51},
            {"position": 3, "team": "UE Porreres", "played": 27, "wins": 12, "draws": 5, "losses": 10, "goals_for": 27, "goals_against": 29, "goal_difference": -2, "points": 41},
        ],
        match_rows=[
            {"round_name": "Jornada 27", "match_date": date(2026, 3, 22), "match_time": time(18, 0), "home_team": "Atletico Baleares", "away_team": "UD Poblense", "home_score": 2, "away_score": 1},
            {"round_name": "Jornada 27", "match_date": date(2026, 3, 22), "match_time": time(18, 30), "home_team": "UE Porreres", "away_team": "Atletico Baleares", "home_score": 0, "away_score": 0},
            {"round_name": "Jornada 28", "match_date": date(2026, 3, 29), "match_time": time(17, 0), "home_team": "Atletico Baleares", "away_team": "UE Porreres", "home_score": None, "away_score": None},
            {"round_name": "Jornada 28", "match_date": date(2026, 3, 29), "match_time": time(19, 0), "home_team": "UD Poblense", "away_team": "Atletico Baleares", "home_score": None, "away_score": None},
        ],
    )
    seed_competition(
        session,
        code="tercera_rfef_g11",
        name="3a RFEF Grupo 11",
        teams=["RCD Mallorca B", "CD Manacor"],
        standings_rows=[
            {"position": 1, "team": "RCD Mallorca B", "played": 27, "wins": 18, "draws": 5, "losses": 4, "goals_for": 52, "goals_against": 19, "goal_difference": 33, "points": 59},
            {"position": 2, "team": "CD Manacor", "played": 27, "wins": 17, "draws": 5, "losses": 5, "goals_for": 48, "goals_against": 24, "goal_difference": 24, "points": 56},
        ],
        match_rows=[
            {"round_name": "Jornada 26", "match_date": date(2026, 3, 22), "match_time": time(12, 0), "home_team": "RCD Mallorca B", "away_team": "CD Manacor", "home_score": 3, "away_score": 1},
            {"round_name": "Jornada 27", "match_date": date(2026, 3, 28), "match_time": time(18, 0), "home_team": "CD Manacor", "away_team": "RCD Mallorca B", "home_score": None, "away_score": None},
        ],
    )


def add_candidate(
    session,
    *,
    candidate_id: int,
    competition_slug: str,
    content_type: str,
    priority: int,
    created_at: datetime,
    formatted_text: str | None,
    text_draft: str,
    payload_json: dict,
    rewritten_text: str | None = None,
) -> None:
    session.add(
        ContentCandidate(
            id=candidate_id,
            competition_slug=competition_slug,
            content_type=content_type,
            priority=priority,
            text_draft=text_draft,
            formatted_text=formatted_text,
            rewritten_text=rewritten_text,
            payload_json=payload_json,
            source_summary_hash=f"export-base-{candidate_id}",
            status="draft",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.commit()


def build_service(session, tmp_path: Path) -> tuple[ExportBaseService, Path]:
    export_path = tmp_path / "exports" / "export_base.json"
    return (
        ExportBaseService(
            session,
            settings=build_settings(app_root=tmp_path),
            output_path=export_path,
        ),
        export_path,
    )


def test_export_base_service_builds_weekly_snapshot_from_editorial_window(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_export_base_context(session)
        created_at = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)

        add_candidate(
            session,
            candidate_id=1,
            competition_slug="segunda_rfef_g3_baleares",
            content_type="preview",
            priority=90,
            created_at=created_at,
            formatted_text="formatted preview",
            rewritten_text="rewrite preview",
            text_draft="draft preview",
            payload_json={
                "content_key": "preview:j28",
                "reference_date": "2026-03-21",
                "source_payload": {
                    "featured_match": {"round_name": "Jornada 28", "match_date": "2026-03-29", "home_team": "Atletico Baleares", "away_team": "UE Porreres"},
                    "matches": [
                        {"round_name": "Jornada 28", "match_date": "2026-03-29", "home_team": "Atletico Baleares", "away_team": "UE Porreres"},
                        {"round_name": "Jornada 28", "match_date": "2026-03-29", "home_team": "UD Poblense", "away_team": "Atletico Baleares"},
                    ],
                },
            },
        )
        add_candidate(
            session,
            candidate_id=2,
            competition_slug="segunda_rfef_g3_baleares",
            content_type="preview",
            priority=95,
            created_at=created_at,
            formatted_text="stale preview",
            text_draft="stale preview",
            payload_json={
                "content_key": "preview:j27",
                "reference_date": "2026-03-18",
                "source_payload": {
                    "featured_match": {"round_name": "Jornada 27", "match_date": "2026-03-22", "home_team": "Atletico Baleares", "away_team": "UD Poblense"},
                    "matches": [
                        {"round_name": "Jornada 27", "match_date": "2026-03-22", "home_team": "Atletico Baleares", "away_team": "UD Poblense"},
                    ],
                },
            },
        )
        add_candidate(
            session,
            candidate_id=3,
            competition_slug="segunda_rfef_g3_baleares",
            content_type="ranking",
            priority=80,
            created_at=created_at,
            formatted_text="",
            text_draft="draft ranking fallback",
            payload_json={
                "content_key": "ranking:overview",
                "reference_date": "2026-03-25",
                "source_payload": {
                    "best_attack": {"team": "Atletico Baleares", "value": 39},
                },
            },
        )
        add_candidate(
            session,
            candidate_id=4,
            competition_slug="tercera_rfef_g11",
            content_type="results_roundup",
            priority=95,
            created_at=created_at,
            formatted_text="formatted results",
            text_draft="draft results",
            payload_json={
                "content_key": "results:j26",
                "reference_date": "2026-03-23",
                "source_payload": {
                    "group_label": "Jornada 26",
                    "matches": [
                        {"round_name": "Jornada 26", "match_date": "2026-03-22", "home_team": "RCD Mallorca B", "away_team": "CD Manacor", "home_score": 3, "away_score": 1},
                    ],
                },
            },
        )
        add_candidate(
            session,
            candidate_id=5,
            competition_slug="tercera_rfef_g11",
            content_type="results_roundup",
            priority=99,
            created_at=created_at,
            formatted_text="old results",
            text_draft="old results",
            payload_json={
                "content_key": "results:j25",
                "reference_date": "2026-03-16",
                "source_payload": {
                    "group_label": "Jornada 25",
                    "matches": [
                        {"round_name": "Jornada 25", "match_date": "2026-03-15", "home_team": "RCD Mallorca B", "away_team": "CD Manacor", "home_score": 1, "away_score": 0},
                    ],
                },
            },
        )
        add_candidate(
            session,
            candidate_id=6,
            competition_slug="segunda_rfef_g3_baleares",
            content_type="metric_narrative",
            priority=81,
            created_at=created_at,
            formatted_text="formatted metric high",
            text_draft="draft metric high",
            payload_json={
                "content_key": "metric:goals_average",
                "reference_date": "2026-03-25",
                "source_payload": {
                    "narrative_type": "goals_average",
                    "metric_value": 2.33,
                },
            },
        )
        add_candidate(
            session,
            candidate_id=7,
            competition_slug="segunda_rfef_g3_baleares",
            content_type="metric_narrative",
            priority=70,
            created_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
            formatted_text="formatted metric low",
            text_draft="draft metric low",
            payload_json={
                "content_key": "metric:goals_average",
                "reference_date": "2026-03-24",
                "source_payload": {
                    "narrative_type": "goals_average",
                    "metric_value": 2.31,
                },
            },
        )
        add_candidate(
            session,
            candidate_id=8,
            competition_slug="tercera_rfef_g11",
            content_type="ranking",
            priority=77,
            created_at=created_at,
            formatted_text="formatted ranking tercera",
            text_draft="draft ranking tercera",
            payload_json={
                "content_key": "ranking:overview",
                "reference_date": "2026-03-25",
                "source_payload": {
                    "best_attack": {"team": "RCD Mallorca B", "value": 52},
                },
            },
        )
        add_candidate(
            session,
            candidate_id=9,
            competition_slug="tercera_rfef_g11",
            content_type="viral_story",
            priority=79,
            created_at=created_at,
            formatted_text=None,
            text_draft="draft excluded",
            payload_json={
                "content_key": "viral:excluded",
                "reference_date": "2026-03-25",
                "source_payload": {
                    "story_type": "hot_form",
                },
            },
        )

        service, export_path = build_service(session, tmp_path)
        result = service.generate_export_file(reference_date=date(2026, 3, 25), dry_run=False)
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        assert result.scope == "weekly_snapshot"
        assert result.target_date == date(2026, 3, 25)
        assert result.window_start == date(2026, 3, 23)
        assert result.window_end == date(2026, 3, 29)
        assert payload["scope"] == "weekly_snapshot"
        assert payload["target_date"] == "2026-03-25"
        assert payload["window_start"] == "2026-03-23"
        assert payload["window_end"] == "2026-03-29"
        assert payload["total_items"] == 5
        assert list(payload["competitions"]) == ["segunda_rfef_g3_baleares", "tercera_rfef_g11"]
        assert [row["id"] for row in payload["competitions"]["segunda_rfef_g3_baleares"]["metric_narrative"]] == [6]
        assert payload["competitions"]["segunda_rfef_g3_baleares"]["metric_narrative"][0]["text"] == "formatted metric high"
        assert payload["competitions"]["segunda_rfef_g3_baleares"]["preview"][0]["selected_text_source"] == "rewritten_text"
        assert payload["competitions"]["segunda_rfef_g3_baleares"]["preview"][0]["text"] == "rewrite preview"
        assert payload["competitions"]["segunda_rfef_g3_baleares"]["ranking"][0]["selected_text_source"] == "text_draft"
        assert payload["competitions"]["segunda_rfef_g3_baleares"]["ranking"][0]["text"] == "draft ranking fallback"
        assert [row["id"] for row in payload["competitions"]["tercera_rfef_g11"]["results_roundup"]] == [4]
        assert [row["id"] for row in payload["competitions"]["tercera_rfef_g11"]["ranking"]] == [8]
    finally:
        session.close()


def test_export_base_service_overwrites_output_file_with_weekly_snapshot(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_export_base_context(session)
        created_at = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
        add_candidate(
            session,
            candidate_id=10,
            competition_slug="segunda_rfef_g3_baleares",
            content_type="ranking",
            priority=90,
            created_at=created_at,
            formatted_text="formatted ranking",
            text_draft="draft ranking",
            payload_json={
                "content_key": "ranking:overview",
                "reference_date": "2026-03-25",
                "source_payload": {"best_attack": {"team": "Atletico Baleares", "value": 39}},
            },
        )

        service, export_path = build_service(session, tmp_path)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text('{"stale": true}', encoding="utf-8")

        service.generate_export_file(reference_date=date(2026, 3, 25), dry_run=False)
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        assert "stale" not in payload
        assert payload["scope"] == "weekly_snapshot"
        assert payload["total_items"] == 1
        assert payload["competitions"]["segunda_rfef_g3_baleares"]["ranking"][0]["id"] == 10
    finally:
        session.close()


def test_export_base_service_uses_viral_preview_text_with_team_handle_in_key_match(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_export_base_context(session)
        session.add(
            TeamMention(
                team_name="Atletico Baleares",
                twitter_handle="@atleticbalears",
                competition_slug="segunda_rfef_g3_baleares",
            )
        )
        session.commit()
        created_at = datetime(2026, 3, 25, 10, 0, tzinfo=timezone.utc)

        add_candidate(
            session,
            candidate_id=11,
            competition_slug="segunda_rfef_g3_baleares",
            content_type="preview",
            priority=92,
            created_at=created_at,
            formatted_text="formatted preview",
            text_draft="draft preview",
            payload_json={
                "content_key": "preview:j28:mentions",
                "competition_name": "2a RFEF Grupo 3",
                "reference_date": "2026-03-25",
                "source_payload": {
                    "featured_match": {
                        "round_name": "Jornada 28",
                        "match_date": "2026-03-29",
                        "home_team": "Atletico Baleares",
                        "away_team": "UE Porreres",
                    },
                    "matches": [
                        {
                            "round_name": "Jornada 28",
                            "match_date": "2026-03-29",
                            "home_team": "Atletico Baleares",
                            "away_team": "UE Porreres",
                        },
                        {
                            "round_name": "Jornada 28",
                            "match_date": "2026-03-29",
                            "home_team": "UD Poblense",
                            "away_team": "Atletico Baleares",
                        },
                    ],
                },
            },
        )

        service, export_path = build_service(session, tmp_path)
        result = service.generate_export_file(reference_date=date(2026, 3, 25), dry_run=False)
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        preview_row = payload["competitions"]["segunda_rfef_g3_baleares"]["preview"][0]

        assert result.total_items == 1
        assert preview_row["id"] == 11
        assert preview_row["selected_text_source"] == "viral_formatted_text"
        assert "Partidos:\nAtlético Baleares vs UE Porreres" in preview_row["text"]
        assert "Partido clave:\n@atleticbalears vs UE Porreres" in preview_row["text"]
        assert preview_row["text"].count("@atleticbalears") == 1
    finally:
        session.close()
