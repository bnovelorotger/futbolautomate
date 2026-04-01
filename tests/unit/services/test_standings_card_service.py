from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.db.models import ContentCandidate
from app.services.image_renderer import render_standings_html
from app.services.standings_card_service import generate_standings_card
from app.services.standings_image_mapper import build_standings_image_context
from tests.unit.services.service_test_support import build_session
from tests.unit.services.test_editorial_narratives import seed_competition


def _candidate(
    *,
    competition_slug: str = "tercera_rfef_g11",
    candidate_id: int = 41,
    payload_json: dict | None = None,
) -> ContentCandidate:
    created_at = datetime(2026, 3, 31, 9, 0, tzinfo=timezone.utc)
    return ContentCandidate(
        id=candidate_id,
        competition_slug=competition_slug,
        content_type="standings_roundup",
        priority=82,
        text_draft="Clasificacion base",
        payload_json=payload_json
        or {
            "competition_name": "3a RFEF Baleares",
            "reference_date": "2026-03-31",
            "source_payload": {
                "round_name": "Jornada 26",
                "group_label": "Grupo A",
                "rows": [
                    {
                        "position": 1,
                        "team": "CE Alpha",
                        "played": 26,
                        "wins": 16,
                        "draws": 6,
                        "losses": 4,
                        "goal_difference": 19,
                        "points": 54,
                        "zone_tag": "playoff",
                    },
                    {
                        "position": 2,
                        "team": "CE Beta",
                        "played": 26,
                        "points": 51,
                    },
                    {
                        "position": 3,
                        "team": "CE Gamma",
                        "played": 26,
                        "points": 48,
                        "zone_tag": "relegation",
                    },
                ],
            },
        },
        source_summary_hash=f"standings-card-{candidate_id}",
        status="published",
        published_at=created_at,
        created_at=created_at,
        updated_at=created_at,
    )


def test_build_standings_image_context_maps_payload_rows() -> None:
    context = build_standings_image_context(_candidate(), max_rows=2)

    assert context["title"] == "CLASIFICACIÓN"
    assert context["competition_name"] == "3a RFEF Baleares"
    assert context["competition_slug"] == "tercera_rfef_g11"
    assert context["round_label"] == "Jornada 26"
    assert context["group_label"] == "Grupo A"
    assert context["season_label"] is None
    assert context["updated_at"] == "2026-03-31"
    assert context["total_teams"] == 3
    assert context["visible_rows"] == 2
    assert context["tracked_teams_present"] == []
    assert context["has_tracked_teams"] is False
    assert context["columns"] == {"won": True, "drawn": True, "lost": True, "goal_diff": True}
    assert context["layout"]["width"] == 1200
    assert context["layout"]["height"] == 1500
    assert context["layout"]["max_rows"] == 2
    assert context["layout"]["table_grid_columns"] == "58px minmax(0, 2.8fr) 68px 62px 54px 54px 54px 68px 84px"
    assert context["rows"] == [
        {
            "position": 1,
            "team_name": "CE Alpha",
            "points": 54,
            "played": 26,
            "won": 16,
            "drawn": 6,
            "lost": 4,
            "goal_diff": 19,
            "zone": "playoff",
            "is_leader": True,
            "is_tracked_team": False,
        },
        {
            "position": 2,
            "team_name": "CE Beta",
            "points": 51,
            "played": 26,
            "won": None,
            "drawn": None,
            "lost": None,
            "goal_diff": None,
            "zone": "playoff",
            "is_leader": False,
            "is_tracked_team": False,
        },
    ]


def test_build_standings_image_context_uses_full_standings_from_session_instead_of_payload_excerpt() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="tercera_rfef_g11",
            name="3a RFEF Grupo 11",
            teams=["CE Alpha", "CE Beta", "CE Gamma", "CE Delta", "CE Epsilon", "CE Zeta"],
            standings_rows=[
                {"position": 1, "team": "CE Alpha", "played": 26, "wins": 17, "draws": 5, "losses": 4, "goals_for": 48, "goals_against": 20, "goal_difference": 28, "points": 56},
                {"position": 2, "team": "CE Beta", "played": 26, "wins": 15, "draws": 6, "losses": 5, "goals_for": 42, "goals_against": 24, "goal_difference": 18, "points": 51},
                {"position": 3, "team": "CE Gamma", "played": 26, "wins": 14, "draws": 7, "losses": 5, "goals_for": 39, "goals_against": 25, "goal_difference": 14, "points": 49},
                {"position": 4, "team": "CE Delta", "played": 26, "wins": 13, "draws": 7, "losses": 6, "goals_for": 36, "goals_against": 25, "goal_difference": 11, "points": 46},
                {"position": 5, "team": "CE Epsilon", "played": 26, "wins": 12, "draws": 7, "losses": 7, "goals_for": 34, "goals_against": 27, "goal_difference": 7, "points": 43},
                {"position": 14, "team": "CE Zeta", "played": 26, "wins": 5, "draws": 7, "losses": 14, "goals_for": 24, "goals_against": 43, "goal_difference": -19, "points": 22},
            ],
            match_rows=[],
        )
        candidate = _candidate(
            candidate_id=410,
            payload_json={
                "competition_name": "3a RFEF Baleares",
                "reference_date": "2026-03-31",
                "source_payload": {
                    "round_name": "Jornada 26",
                    "rows": [
                        {"position": 1, "team": "CE Alpha", "played": 26, "points": 56},
                        {"position": 2, "team": "CE Beta", "played": 26, "points": 51},
                    ],
                },
            },
        )
        session.add(candidate)
        session.commit()

        context = build_standings_image_context(candidate)

        assert context["total_teams"] == 6
        assert context["visible_rows"] == 6
        assert [row["position"] for row in context["rows"]] == [1, 2, 3, 4, 5, 14]
        assert context["rows"][0]["team_name"] == "CE Alpha"
        assert context["rows"][0]["is_leader"] is True
        assert context["rows"][1]["zone"] == "playoff"
        assert context["rows"][4]["zone"] == "playoff"
        assert context["rows"][5]["zone"] == "relegation"
    finally:
        session.close()


def test_build_standings_image_context_marks_tracked_teams_inside_full_standings() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="segunda_rfef_g3_baleares",
            name="2a RFEF Grupo 3",
            teams=["UE Sant Andreu", "CD Atletico Baleares", "UD Poblense", "Reus FC Reddis", "UE Porreres"],
            standings_rows=[
                {"position": 1, "team": "UE Sant Andreu", "played": 28, "wins": 18, "draws": 5, "losses": 5, "goals_for": 47, "goals_against": 24, "goal_difference": 23, "points": 59},
                {"position": 2, "team": "CD Atletico Baleares", "played": 28, "wins": 16, "draws": 7, "losses": 5, "goals_for": 42, "goals_against": 25, "goal_difference": 17, "points": 55},
                {"position": 5, "team": "UD Poblense", "played": 28, "wins": 13, "draws": 7, "losses": 8, "goals_for": 39, "goals_against": 31, "goal_difference": 8, "points": 46},
                {"position": 7, "team": "Reus FC Reddis", "played": 28, "wins": 11, "draws": 8, "losses": 9, "goals_for": 34, "goals_against": 32, "goal_difference": 2, "points": 41},
                {"position": 14, "team": "UE Porreres", "played": 28, "wins": 8, "draws": 6, "losses": 14, "goals_for": 27, "goals_against": 41, "goal_difference": -14, "points": 30},
            ],
            match_rows=[],
        )
        candidate = _candidate(
            competition_slug="segunda_rfef_g3_baleares",
            candidate_id=411,
            payload_json={
                "competition_name": "2a RFEF con equipos baleares",
                "reference_date": "2026-03-31",
                "source_payload": {
                    "round_name": "Jornada 28",
                    "rows": [
                        {"position": 2, "team": "CD Atletico Baleares", "played": 28, "points": 55},
                        {"position": 5, "team": "UD Poblense", "played": 28, "points": 46},
                    ],
                },
            },
        )
        session.add(candidate)
        session.commit()

        context = build_standings_image_context(candidate)
        tracked_by_team = {row["team_name"]: row["is_tracked_team"] for row in context["rows"]}

        assert context["total_teams"] == 5
        assert context["has_tracked_teams"] is True
        assert context["tracked_teams_present"] == ["Atletico Baleares", "UD Poblense", "UE Porreres"]
        assert tracked_by_team["CD Atletico Baleares"] is True
        assert tracked_by_team["UD Poblense"] is True
        assert tracked_by_team["UE Porreres"] is True
        assert tracked_by_team["UE Sant Andreu"] is False
        assert tracked_by_team["Reus FC Reddis"] is False
    finally:
        session.close()


def test_build_standings_image_context_handles_competitions_without_zones_or_tracked_teams() -> None:
    session = build_session()
    try:
        seed_competition(
            session,
            code="division_honor_mallorca",
            name="Division Honor Mallorca",
            teams=["CE Norte", "CE Centro", "CE Sur"],
            standings_rows=[
                {"position": 1, "team": "CE Norte", "played": 24, "wins": 16, "draws": 5, "losses": 3, "goals_for": 38, "goals_against": 18, "goal_difference": 20, "points": 53},
                {"position": 2, "team": "CE Centro", "played": 24, "wins": 15, "draws": 4, "losses": 5, "goals_for": 33, "goals_against": 21, "goal_difference": 12, "points": 49},
                {"position": 3, "team": "CE Sur", "played": 24, "wins": 13, "draws": 5, "losses": 6, "goals_for": 31, "goals_against": 25, "goal_difference": 6, "points": 44},
            ],
            match_rows=[],
        )
        candidate = _candidate(
            competition_slug="division_honor_mallorca",
            candidate_id=412,
            payload_json={
                "competition_name": "Division Honor Mallorca",
                "reference_date": "2026-03-31",
                "source_payload": {
                    "round_name": "Jornada 24",
                    "rows": [
                        {"position": 1, "team": "CE Norte", "played": 24, "points": 53},
                    ],
                },
            },
        )
        session.add(candidate)
        session.commit()

        context = build_standings_image_context(candidate)

        assert context["total_teams"] == 3
        assert [row["position"] for row in context["rows"]] == [1, 2, 3]
        assert context["rows"][0]["is_leader"] is True
        assert all(row["zone"] is None for row in context["rows"])
        assert all(row["is_tracked_team"] is False for row in context["rows"])
        assert context["has_tracked_teams"] is False
        assert context["tracked_teams_present"] == []
    finally:
        session.close()


def test_generate_standings_card_writes_expected_relative_paths(tmp_path: Path, monkeypatch) -> None:
    export_root = tmp_path / "exports"
    candidate = _candidate(candidate_id=77)
    recorded: dict[str, object] = {}

    def fake_render(context: dict, output_html_path: Path) -> Path:
        output_html_path.parent.mkdir(parents=True, exist_ok=True)
        output_html_path.write_text("<html></html>", encoding="utf-8")
        recorded["context"] = context
        recorded["html_path"] = output_html_path
        return output_html_path

    def fake_png(html_path: Path, png_path: Path, width: int = 1200, height: int = 1500) -> Path:
        png_path.parent.mkdir(parents=True, exist_ok=True)
        png_path.write_bytes(b"png")
        recorded["png_path"] = png_path
        recorded["html_input"] = html_path
        recorded["size"] = (width, height)
        return png_path

    monkeypatch.setattr("app.services.standings_card_service.render_standings_html", fake_render)
    monkeypatch.setattr("app.services.standings_card_service.html_to_png", fake_png)

    image_path = generate_standings_card(candidate, output_root=export_root, width=1200, height=1500, max_rows=10)

    expected_html = export_root / "tmp" / "images" / "tercera_rfef_g11" / "2026-03-31" / "standings_roundup_77.html"
    expected_png = export_root / "images" / "tercera_rfef_g11" / "2026-03-31" / "standings_roundup_77.png"

    assert image_path == "exports/images/tercera_rfef_g11/2026-03-31/standings_roundup_77.png"
    assert recorded["html_path"] == expected_html
    assert recorded["png_path"] == expected_png
    assert recorded["html_input"] == expected_html
    assert recorded["size"] == (1200, 1500)
    assert expected_html.exists()
    assert expected_png.exists()
    assert recorded["context"]["total_teams"] == 3
    assert recorded["context"]["layout"]["width"] == 1200
    assert recorded["context"]["layout"]["height"] == 1500
    assert recorded["context"]["layout"]["max_rows"] == 3


def test_generate_standings_card_returns_none_when_renderer_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.standings_card_service.render_standings_html",
        lambda context, output_html_path: (_ for _ in ()).throw(RuntimeError("render failed")),
    )

    image_path = generate_standings_card(_candidate(), output_root=tmp_path / "exports")

    assert image_path is None


def test_render_standings_html_keeps_grid_tracks_separated_when_optional_columns_are_enabled(tmp_path: Path) -> None:
    context = build_standings_image_context(_candidate(), max_rows=10)

    html_path = render_standings_html(context, tmp_path / "standings_full.html")
    html = html_path.read_text(encoding="utf-8")

    assert "grid-template-columns: 58px minmax(0, 2.8fr) 68px 62px 54px 54px 54px 68px 84px;" in html
    assert "54px54px" not in html
    assert "54px68px" not in html


def test_render_standings_html_keeps_minimal_grid_valid_without_optional_columns(tmp_path: Path) -> None:
    candidate = _candidate(
        candidate_id=88,
        payload_json={
            "competition_name": "3a RFEF Baleares",
            "reference_date": "2026-03-31",
            "source_payload": {
                "round_name": "Jornada 26",
                "rows": [
                    {
                        "position": 1,
                        "team": "CE Alpha",
                        "played": 26,
                        "points": 54,
                    },
                    {
                        "position": 2,
                        "team": "CE Beta",
                        "played": 26,
                        "points": 51,
                    },
                ],
            },
        },
    )
    context = build_standings_image_context(candidate, max_rows=10)

    html_path = render_standings_html(context, tmp_path / "standings_minimal.html")
    html = html_path.read_text(encoding="utf-8")

    assert "grid-template-columns: 58px minmax(0, 2.8fr) 68px 62px 84px;" in html
    assert "54px54px" not in html
