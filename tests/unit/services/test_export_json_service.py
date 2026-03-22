from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from pathlib import Path

from app.db.models import ContentCandidate
from app.services.export_json_service import ExportJsonService
from tests.unit.services.service_test_support import build_session, build_settings
from tests.unit.services.test_editorial_narratives import seed_competition


def seed_export_context(session) -> None:
    seed_competition(
        session,
        code="segunda_rfef_g3_baleares",
        name="2a RFEF Grupo 3",
        teams=["Atletico Baleares", "UD Poblense", "Torrent CF", "UE Sant Andreu"],
        standings_rows=[
            {"position": 1, "team": "Atletico Baleares", "played": 26, "wins": 17, "draws": 6, "losses": 3, "goals_for": 40, "goals_against": 18, "goal_difference": 22, "points": 57},
            {"position": 2, "team": "UD Poblense", "played": 26, "wins": 15, "draws": 6, "losses": 5, "goals_for": 35, "goals_against": 21, "goal_difference": 14, "points": 51},
            {"position": 3, "team": "UE Sant Andreu", "played": 26, "wins": 14, "draws": 7, "losses": 5, "goals_for": 33, "goals_against": 22, "goal_difference": 11, "points": 49},
            {"position": 4, "team": "Torrent CF", "played": 26, "wins": 12, "draws": 5, "losses": 9, "goals_for": 28, "goals_against": 26, "goal_difference": 2, "points": 41},
        ],
        match_rows=[
            {"round_name": "Jornada 26", "match_date": date(2026, 3, 16), "match_time": time(18, 0), "home_team": "Atletico Baleares", "away_team": "Torrent CF", "home_score": 2, "away_score": 0},
            {"round_name": "Jornada 26", "match_date": date(2026, 3, 16), "match_time": time(18, 30), "home_team": "UE Sant Andreu", "away_team": "UD Poblense", "home_score": 1, "away_score": 1},
            {"round_name": "Jornada 27", "match_date": date(2026, 3, 21), "match_time": time(17, 0), "home_team": "Atletico Baleares", "away_team": "UD Poblense", "home_score": None, "away_score": None},
            {"round_name": "Jornada 27", "match_date": date(2026, 3, 21), "match_time": time(19, 0), "home_team": "UE Sant Andreu", "away_team": "Torrent CF", "home_score": None, "away_score": None},
        ],
    )


def add_candidate(
    session,
    *,
    candidate_id: int,
    content_type: str,
    text_draft: str,
    payload_json: dict,
    created_at: datetime,
    rewritten_text: str | None = None,
    formatted_text: str | None = None,
) -> None:
    session.add(
        ContentCandidate(
            id=candidate_id,
            competition_slug="segunda_rfef_g3_baleares",
            content_type=content_type,
            priority=90,
            text_draft=text_draft,
            rewritten_text=rewritten_text,
            formatted_text=formatted_text,
            payload_json=payload_json,
            source_summary_hash=f"export-json-{candidate_id}",
            status="published",
            reviewed_at=created_at,
            approved_at=created_at,
            published_at=created_at,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.commit()


def build_results_payload(
    *,
    round_name: str,
    matches: list[dict],
    part_index: int | None = None,
    part_total: int | None = None,
) -> dict:
    source_payload = {
        "group_label": round_name,
        "selected_matches_count": len(matches),
        "omitted_matches_count": 0,
        "matches": matches,
    }
    if part_index is not None and part_total is not None:
        source_payload["part_index"] = part_index
        source_payload["part_total"] = part_total
    return {
        "competition_name": "2a RFEF Grupo 3",
        "reference_date": "2026-03-17",
        "source_payload": source_payload,
    }


def build_standings_payload(
    *,
    round_name: str,
    rows: list[dict],
    part_index: int | None = None,
    part_total: int | None = None,
    split_focus: str | None = None,
) -> dict:
    source_payload = {
        "group_label": round_name,
        "round_name": round_name,
        "selected_rows_count": len(rows),
        "omitted_rows_count": 0,
        "rows": rows,
    }
    if part_index is not None and part_total is not None:
        source_payload["part_index"] = part_index
        source_payload["part_total"] = part_total
    if split_focus is not None:
        source_payload["split_focus"] = split_focus
    return {
        "competition_name": "2a RFEF Grupo 3",
        "reference_date": "2026-03-17",
        "source_payload": source_payload,
    }


def build_service(session, tmp_path: Path) -> tuple[ExportJsonService, Path]:
    export_path = tmp_path / "export" / "export_base.json"
    return (
        ExportJsonService(
            session,
            settings=build_settings(app_root=tmp_path),
            output_path=export_path,
        ),
        export_path,
    )


def test_export_json_service_filters_jornadas_and_overwrites_file(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_export_context(session)
        created_at = datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc)
        add_candidate(
            session,
            candidate_id=1,
            content_type="results_roundup",
            text_draft="Base resultados",
            payload_json=build_results_payload(
                round_name="Jornada 26",
                matches=[
                    {"round_name": "Jornada 26", "match_date": "2026-03-16", "home_team": "Atletico Baleares", "away_team": "Torrent CF", "home_score": 2, "away_score": 0},
                    {"round_name": "Jornada 26", "match_date": "2026-03-16", "home_team": "UE Sant Andreu", "away_team": "UD Poblense", "home_score": 1, "away_score": 1},
                ],
            ),
            created_at=created_at,
        )
        add_candidate(
            session,
            candidate_id=2,
            content_type="results_roundup",
            text_draft="Legacy resultados",
            payload_json={
                "competition_name": "2a RFEF Grupo 3",
                "reference_date": "2026-03-10",
                "source_payload": {
                    "group_label": "Jornada 25",
                    "selected_matches_count": 1,
                    "omitted_matches_count": 0,
                    "matches": [
                        {"round_name": "Jornada 25", "match_date": "2026-03-09", "home_team": "Atletico Baleares", "away_team": "Torrent CF", "home_score": 1, "away_score": 0},
                    ],
                },
            },
            created_at=created_at,
        )
        add_candidate(
            session,
            candidate_id=3,
            content_type="ranking",
            text_draft="Ranking base",
            payload_json={
                "competition_name": "2a RFEF Grupo 3",
                "reference_date": "2026-03-17",
                "source_payload": {
                    "best_attack": {"team": "Atletico Baleares", "value": 40},
                    "best_defense": {"team": "UD Poblense", "value": 21},
                    "most_wins": {"team": "UE Sant Andreu", "value": 14},
                },
            },
            created_at=created_at,
        )
        add_candidate(
            session,
            candidate_id=4,
            content_type="preview",
            text_draft="Preview base",
            payload_json={
                "competition_name": "2a RFEF Grupo 3",
                "reference_date": "2026-03-17",
                "source_payload": {
                    "featured_match": {"round_name": "Jornada 27", "match_date": "2026-03-21", "home_team": "Atletico Baleares", "away_team": "UD Poblense"},
                    "matches": [
                        {"round_name": "Jornada 27", "match_date": "2026-03-21", "home_team": "Atletico Baleares", "away_team": "UD Poblense"},
                        {"round_name": "Jornada 27", "match_date": "2026-03-21", "home_team": "UE Sant Andreu", "away_team": "Torrent CF"},
                    ],
                },
            },
            created_at=created_at,
            rewritten_text=(
                "🔎 Previa - 2ª RFEF - G3 - J27\n\n"
                "Partidos:\nAtletico Baleares vs UD Poblense\nUE Sant Andreu vs Torrent CF\n\n"
                "Partido clave:\nAtletico Baleares vs UD Poblense\n\n#FutbolBalear #2aRFEF"
            ),
        )

        service, export_path = build_service(session, tmp_path)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text("[]", encoding="utf-8")

        result = service.generate_export_file(reference_date=date(2026, 3, 17), dry_run=False)
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        assert result.generated_count == 3
        assert result.blocked_series_count == 0
        assert [row["content_type"] for row in payload] == ["results_roundup", "ranking", "preview"]
        assert {row["id"] for row in payload} == {1, 3, 4}
        assert payload[0]["match_date"] == "2026-03-16"
        assert payload[1]["competition"] == "2ª RFEF"
        assert payload[2]["tweet"].startswith("🔎 Previa - 2ª RFEF - G3 - J27")
    finally:
        session.close()


def test_export_json_service_exports_complete_standings_series(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_export_context(session)
        created_at = datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc)
        add_candidate(
            session,
            candidate_id=11,
            content_type="standings_roundup",
            text_draft="Standings top",
            payload_json=build_standings_payload(
                round_name="Jornada 26",
                part_index=1,
                part_total=2,
                split_focus="top",
                rows=[
                    {"position": 1, "team": "Atletico Baleares", "played": 26, "points": 57},
                    {"position": 2, "team": "UD Poblense", "played": 26, "points": 51, "zone_tag": "playoff"},
                ],
            ),
            created_at=created_at,
        )
        add_candidate(
            session,
            candidate_id=12,
            content_type="standings_roundup",
            text_draft="Standings relegation",
            payload_json=build_standings_payload(
                round_name="Jornada 26",
                part_index=2,
                part_total=2,
                split_focus="relegation",
                rows=[
                    {"position": 14, "team": "Torrent CF", "played": 26, "points": 30, "zone_tag": "relegation"},
                ],
            ),
            created_at=created_at,
        )

        service, export_path = build_service(session, tmp_path)
        result = service.generate_export_file(reference_date=date(2026, 3, 17), dry_run=False)
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        assert result.generated_count == 2
        assert result.blocked_series_count == 0
        assert [row["id"] for row in payload] == [11, 12]
    finally:
        session.close()


def test_export_json_service_blocks_standings_series_when_part_one_is_missing(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_export_context(session)
        created_at = datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc)
        add_candidate(
            session,
            candidate_id=21,
            content_type="standings_roundup",
            text_draft="Standings relegation only",
            payload_json=build_standings_payload(
                round_name="Jornada 26",
                part_index=2,
                part_total=2,
                split_focus="relegation",
                rows=[
                    {"position": 14, "team": "Torrent CF", "played": 26, "points": 30, "zone_tag": "relegation"},
                ],
            ),
            created_at=created_at,
        )

        service, export_path = build_service(session, tmp_path)
        result = service.generate_export_file(reference_date=date(2026, 3, 17), dry_run=False)
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        assert result.generated_count == 0
        assert result.blocked_series_count == 1
        assert result.blocked_series[0].blocked_reason == "partition_series_incomplete"
        assert result.blocked_series[0].expected_parts == [1, 2]
        assert result.blocked_series[0].available_parts == [2]
        assert payload == []
    finally:
        session.close()


def test_export_json_service_blocks_standings_series_when_part_two_is_missing(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_export_context(session)
        created_at = datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc)
        add_candidate(
            session,
            candidate_id=22,
            content_type="standings_roundup",
            text_draft="Standings top only",
            payload_json=build_standings_payload(
                round_name="Jornada 26",
                part_index=1,
                part_total=2,
                split_focus="top",
                rows=[
                    {"position": 1, "team": "Atletico Baleares", "played": 26, "points": 57},
                    {"position": 2, "team": "UD Poblense", "played": 26, "points": 51, "zone_tag": "playoff"},
                ],
            ),
            created_at=created_at,
        )

        service, export_path = build_service(session, tmp_path)
        result = service.generate_export_file(reference_date=date(2026, 3, 17), dry_run=False)
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        assert result.generated_count == 0
        assert result.blocked_series_count == 1
        assert result.blocked_series[0].blocked_reason == "partition_series_incomplete"
        assert result.blocked_series[0].expected_parts == [1, 2]
        assert result.blocked_series[0].available_parts == [1]
        assert payload == []
    finally:
        session.close()


def test_export_json_service_exports_complete_results_series(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_export_context(session)
        created_at = datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc)
        add_candidate(
            session,
            candidate_id=31,
            content_type="results_roundup",
            text_draft="Resultados 1/3",
            payload_json=build_results_payload(
                round_name="Jornada 26",
                part_index=1,
                part_total=3,
                matches=[
                    {"round_name": "Jornada 26", "match_date": "2026-03-16", "home_team": "Atletico Baleares", "away_team": "Torrent CF", "home_score": 2, "away_score": 0},
                ],
            ),
            created_at=created_at,
        )
        add_candidate(
            session,
            candidate_id=32,
            content_type="results_roundup",
            text_draft="Resultados 2/3",
            payload_json=build_results_payload(
                round_name="Jornada 26",
                part_index=2,
                part_total=3,
                matches=[
                    {"round_name": "Jornada 26", "match_date": "2026-03-16", "home_team": "UE Sant Andreu", "away_team": "UD Poblense", "home_score": 1, "away_score": 1},
                ],
            ),
            created_at=created_at,
        )
        add_candidate(
            session,
            candidate_id=33,
            content_type="results_roundup",
            text_draft="Resultados 3/3",
            payload_json=build_results_payload(
                round_name="Jornada 26",
                part_index=3,
                part_total=3,
                matches=[
                    {"round_name": "Jornada 26", "match_date": "2026-03-16", "home_team": "Torrent CF", "away_team": "Atletico Baleares", "home_score": 0, "away_score": 1},
                ],
            ),
            created_at=created_at,
        )

        service, export_path = build_service(session, tmp_path)
        result = service.generate_export_file(reference_date=date(2026, 3, 17), dry_run=False)
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        assert result.generated_count == 3
        assert result.blocked_series_count == 0
        assert [row["id"] for row in payload] == [31, 32, 33]
    finally:
        session.close()


def test_export_json_service_blocks_results_series_with_missing_middle_part(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_export_context(session)
        created_at = datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc)
        add_candidate(
            session,
            candidate_id=41,
            content_type="results_roundup",
            text_draft="Resultados 1/3",
            payload_json=build_results_payload(
                round_name="Jornada 26",
                part_index=1,
                part_total=3,
                matches=[
                    {"round_name": "Jornada 26", "match_date": "2026-03-16", "home_team": "Atletico Baleares", "away_team": "Torrent CF", "home_score": 2, "away_score": 0},
                ],
            ),
            created_at=created_at,
        )
        add_candidate(
            session,
            candidate_id=43,
            content_type="results_roundup",
            text_draft="Resultados 3/3",
            payload_json=build_results_payload(
                round_name="Jornada 26",
                part_index=3,
                part_total=3,
                matches=[
                    {"round_name": "Jornada 26", "match_date": "2026-03-16", "home_team": "Torrent CF", "away_team": "Atletico Baleares", "home_score": 0, "away_score": 1},
                ],
            ),
            created_at=created_at,
        )

        service, export_path = build_service(session, tmp_path)
        result = service.generate_export_file(reference_date=date(2026, 3, 17), dry_run=False)
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        assert result.generated_count == 0
        assert result.blocked_series_count == 1
        assert result.blocked_series[0].blocked_reason == "partition_series_incomplete"
        assert result.blocked_series[0].expected_parts == [1, 2, 3]
        assert result.blocked_series[0].available_parts == [1, 3]
        assert payload == []
    finally:
        session.close()


def test_export_json_service_blocks_series_when_one_part_has_invalid_title(tmp_path: Path) -> None:
    session = build_session()
    try:
        seed_export_context(session)
        created_at = datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc)
        add_candidate(
            session,
            candidate_id=51,
            content_type="standings_roundup",
            text_draft="Standings top invalid title",
            payload_json=build_standings_payload(
                round_name="Jornada 26",
                part_index=1,
                part_total=2,
                split_focus="top",
                rows=[
                    {"position": 1, "team": "Atletico Baleares", "played": 26, "points": 57},
                    {"position": 2, "team": "UD Poblense", "played": 26, "points": 51, "zone_tag": "playoff"},
                ],
            ),
            created_at=created_at,
            rewritten_text=(
                "📊 Clasificación - 2ª RFEF - G3 (1/2)\n\n"
                "1. Atletico Baleares - 57 pts\n"
                "2. UD Poblense - 51 pts [PO]\n\n"
                "#FutbolBalear #2aRFEF"
            ),
        )
        add_candidate(
            session,
            candidate_id=52,
            content_type="standings_roundup",
            text_draft="Standings relegation valid title",
            payload_json=build_standings_payload(
                round_name="Jornada 26",
                part_index=2,
                part_total=2,
                split_focus="relegation",
                rows=[
                    {"position": 14, "team": "Torrent CF", "played": 26, "points": 30, "zone_tag": "relegation"},
                ],
            ),
            created_at=created_at,
        )

        service, export_path = build_service(session, tmp_path)
        result = service.generate_export_file(reference_date=date(2026, 3, 17), dry_run=False)
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        assert result.generated_count == 0
        assert result.blocked_series_count == 1
        assert result.blocked_series[0].blocked_reason == "partition_series_quality_failed"
        assert result.blocked_series[0].expected_parts == [1, 2]
        assert result.blocked_series[0].available_parts == [1, 2]
        assert result.blocked_series[0].passed_parts == [2]
        assert payload == []
    finally:
        session.close()
