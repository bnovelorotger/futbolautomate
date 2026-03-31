from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.db.models import ContentCandidate
from app.services.image_renderer import render_standings_html
from app.services.standings_card_service import generate_standings_card
from app.services.standings_image_mapper import build_standings_image_context


def _candidate(*, candidate_id: int = 41, payload_json: dict | None = None) -> ContentCandidate:
    created_at = datetime(2026, 3, 31, 9, 0, tzinfo=timezone.utc)
    return ContentCandidate(
        id=candidate_id,
        competition_slug="tercera_rfef_g11",
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
    assert context["layout"] == {"width": 1200, "height": 1500, "max_rows": 2}
    assert context["columns"] == {"won": True, "drawn": True, "lost": True, "goal_diff": True}
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
            "zone": None,
        },
    ]


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
    assert recorded["context"]["layout"] == {"width": 1200, "height": 1500, "max_rows": 10}


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

    assert "grid-template-columns: 70px minmax(0, 2.4fr) 78px 78px 64px 64px 64px 78px 96px;" in html
    assert "64px64px" not in html
    assert "64px78px" not in html


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

    assert "grid-template-columns: 70px minmax(0, 2.4fr) 78px 78px 96px;" in html
    assert "64px64px" not in html
