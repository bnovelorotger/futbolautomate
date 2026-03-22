from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import ContentCandidateStatus, ContentType
from app.db.base import Base
from app.db.models import Competition, TeamMention
from app.schemas.editorial_content import ContentCandidateDraft
from app.services.editorial_formatter import EditorialFormatterService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def seed_catalog(session: Session) -> None:
    session.add_all(
        [
            Competition(
                code="tercera_rfef_g11",
                name="3a RFEF Grupo 11",
                normalized_name="3a rfef grupo 11",
                category_level=5,
                gender="male",
                region="Baleares",
                country="Spain",
                federation="RFEF",
            ),
            Competition(
                code="segunda_rfef_g3_baleares",
                name="2a RFEF Grupo 3",
                normalized_name="2a rfef grupo 3",
                category_level=4,
                gender="male",
                region="Baleares",
                country="Spain",
                federation="RFEF",
            ),
        ]
    )
    session.add_all(
        [
            TeamMention(
                team_name="CD Manacor",
                twitter_handle="@cdmanacor",
                competition_slug="tercera_rfef_g11",
            ),
            TeamMention(
                team_name="CD Atletico Baleares",
                twitter_handle="@atleticbalears",
                competition_slug="segunda_rfef_g3_baleares",
            ),
        ]
    )
    session.commit()


def test_format_results_summary_applies_mentions_and_hashtag() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="tercera_rfef_g11",
            content_type=ContentType.RESULTS_ROUNDUP,
            priority=99,
            text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 26",
            source_summary_hash="hash-results",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "3a RFEF Baleares",
                "source_payload": {
                    "group_label": "Jornada 26",
                    "matches": [
                        {
                            "home_team": "CD Manacor",
                            "away_team": "RCD Mallorca B",
                            "home_score": 2,
                            "away_score": 1,
                        },
                        {
                            "home_team": "CE Felanitx",
                            "away_team": "CD Llosetense",
                            "home_score": 1,
                            "away_score": 1,
                        },
                    ],
                },
            },
        )

        formatted = service.apply_to_draft(draft).formatted_text

        assert formatted is not None
        assert formatted.startswith("📋 RESULTADOS")
        assert "@cdmanacor" in formatted
        assert formatted.rstrip().endswith("#TerceraRFEF")
        assert len(formatted) <= 240
    finally:
        session.close()


def test_format_standings_summary_keeps_zone_markers_and_hashtag() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="tercera_rfef_g11",
            content_type=ContentType.STANDINGS_ROUNDUP,
            priority=82,
            text_draft="CLASIFICACION | 3a RFEF Baleares",
            source_summary_hash="hash-standings",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "3a RFEF Baleares",
                "source_payload": {
                    "rows": [
                        {"position": 1, "team": "RCD Mallorca B", "points": 66},
                        {"position": 2, "team": "CD Manacor", "points": 64, "zone_tag": "playoff"},
                        {"position": 14, "team": "CD Son Cladera", "points": 25, "zone_tag": "relegation"},
                    ],
                },
            },
        )

        formatted = service.apply_to_draft(draft).formatted_text

        assert formatted is not None
        assert formatted.startswith("📊 CLASIFICACION")
        assert "[PO]" in formatted
        assert "[DESC]" in formatted
        assert formatted.rstrip().endswith("#TerceraRFEF")
        assert len(formatted) <= 240
    finally:
        session.close()


def test_resolve_team_mention_uses_normalized_identity() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)

        mention = service.resolve_team_mention("Atletico Baleares", "segunda_rfef_g3_baleares")

        assert mention == " @atleticbalears"
    finally:
        session.close()


def test_formatter_reduces_results_summary_when_limit_is_small() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session, max_characters=120)
        draft = ContentCandidateDraft(
            competition_slug="tercera_rfef_g11",
            content_type=ContentType.RESULTS_ROUNDUP,
            priority=99,
            text_draft="RESULTADOS | 3a RFEF Baleares | Jornada 26",
            source_summary_hash="hash-results-small",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "3a RFEF Baleares",
                "source_payload": {
                    "group_label": "Jornada 26",
                    "matches": [
                        {"home_team": "CD Manacor", "away_team": "RCD Mallorca B", "home_score": 2, "away_score": 1},
                        {"home_team": "CE Felanitx", "away_team": "CD Llosetense", "home_score": 1, "away_score": 1},
                        {"home_team": "Inter Ibiza CD", "away_team": "SD Portmany", "home_score": 3, "away_score": 0},
                    ],
                },
            },
        )

        formatted = service.apply_to_draft(draft).formatted_text

        assert formatted is not None
        assert len(formatted) <= 120
        assert formatted.count("\n") >= 3
    finally:
        session.close()


def test_format_narrative_uses_deterministic_streak_template() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="tercera_rfef_g11",
            content_type=ContentType.VIRAL_STORY,
            priority=75,
            text_draft="CD Manacor suma 5 victorias seguidas en 3a RFEF Baleares.",
            source_summary_hash="hash-streak",
            status=ContentCandidateStatus.DRAFT,
            scheduled_at=datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc),
            payload_json={
                "competition_name": "3a RFEF Baleares",
                "source_payload": {
                    "story_type": "win_streak",
                    "team": "CD Manacor",
                    "metric_value": 5,
                },
            },
        )

        formatted = service.apply_to_draft(draft).formatted_text

        assert formatted is not None
        assert formatted.startswith("🔥 RACHA")
        assert "5 partidos consecutivos" in formatted
        assert formatted.rstrip().endswith("#TerceraRFEF")
    finally:
        session.close()


def test_format_preview_summary_produces_compact_preview() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="segunda_rfef_g3_baleares",
            content_type=ContentType.PREVIEW,
            priority=90,
            text_draft="PREVIA DE LA JORNADA",
            source_summary_hash="hash-preview",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "2a RFEF con equipos baleares",
                "source_payload": {
                    "matches": [
                        {
                            "round_name": "Jornada 28",
                            "home_team": "UE Sant Andreu",
                            "away_team": "Atletico Baleares",
                        },
                        {
                            "round_name": "Jornada 28",
                            "home_team": "RCD Espanyol B",
                            "away_team": "UD Poblense",
                        },
                        {
                            "round_name": "Jornada 28",
                            "home_team": "UE Porreres",
                            "away_team": "UE Olot",
                        },
                    ]
                },
            },
        )

        formatted = service.apply_to_draft(draft).formatted_text

        assert formatted is not None
        assert formatted.startswith("PREVIA")
        assert "Jornada 28" in formatted
        assert "UE Sant Andreu vs Atlético Baleares" in formatted
        assert "RCD Espanyol B vs UD Poblense" in formatted
        assert "UE Porreres vs UE Olot" not in formatted
        assert formatted.rstrip().endswith("#SegundaRFEF")
        assert len(formatted) <= 240
        assert formatted.count("\n") <= 6
    finally:
        session.close()


def test_build_text_layers_produce_viral_results_roundup() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="segunda_rfef_g3_baleares",
            content_type=ContentType.RESULTS_ROUNDUP,
            priority=99,
            text_draft="RESULTADOS | 2a RFEF con equipos baleares | Jornada 27",
            source_summary_hash="hash-results-viral",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "2a RFEF con equipos baleares",
                "source_payload": {
                    "matches": [
                        {"home_team": "Atletico Baleares", "away_team": "UE Porreres", "home_score": 2, "away_score": 0},
                        {"home_team": "UD Poblense", "away_team": "Torrent CF", "home_score": 1, "away_score": 1},
                    ],
                },
            },
        )

        layers = service.build_text_layers_for_draft(draft)

        assert layers.viral_formatted_text is not None
        assert layers.viral_formatted_text.startswith("📋 Resultados 2a RFEF con equipos baleares")
        assert "Jornada 27" not in layers.viral_formatted_text
        assert "Atletico Baleares" not in layers.viral_formatted_text
        assert "@atleticbalears 2-0 UE Porreres" in layers.viral_formatted_text
        assert "#FutbolBalear #SegundaRFEF" in layers.viral_formatted_text
        assert layers.viral_formatted_text.count("#") == 2
        assert len(layers.viral_formatted_text) <= 240
    finally:
        session.close()


def test_build_text_layers_produce_viral_preview() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="segunda_rfef_g3_baleares",
            content_type=ContentType.PREVIEW,
            priority=90,
            text_draft="PREVIA DE LA JORNADA",
            source_summary_hash="hash-preview-viral",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "2a RFEF con equipos baleares",
                "source_payload": {
                    "featured_match": {
                        "round_name": "Jornada 28",
                        "home_team": "Atletico Baleares",
                        "away_team": "UD Poblense",
                    }
                },
            },
        )

        layers = service.build_text_layers_for_draft(draft)

        assert layers.viral_formatted_text is not None
        assert layers.viral_formatted_text.startswith("🔎 Previa 2a RFEF con equipos baleares")
        assert "Partido clave:" in layers.viral_formatted_text
        assert "@atleticbalears" in layers.viral_formatted_text
        assert "Jornada 28" in layers.viral_formatted_text
        assert layers.viral_formatted_text.endswith("#FutbolBalear #SegundaRFEF")
        assert len(layers.viral_formatted_text) <= 240
    finally:
        session.close()


def test_build_text_layers_produce_viral_standings_roundup() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="tercera_rfef_g11",
            content_type=ContentType.STANDINGS_ROUNDUP,
            priority=82,
            text_draft="CLASIFICACION | 3a RFEF Baleares",
            source_summary_hash="hash-standings-viral",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "3a RFEF Baleares",
                "source_payload": {
                    "rows": [
                        {"position": 1, "team": "RCD Mallorca B", "points": 66},
                        {"position": 2, "team": "CD Manacor", "points": 64},
                        {"position": 3, "team": "SCR Pena Deportiva", "points": 57},
                        {"position": 4, "team": "CD Llosetense", "points": 46},
                        {"position": 5, "team": "CE Constancia", "points": 40},
                    ],
                },
            },
        )

        layers = service.build_text_layers_for_draft(draft)

        assert layers.viral_formatted_text is not None
        assert layers.viral_formatted_text.startswith("📊 Clasificación 3a RFEF Baleares")
        assert "1. RCD Mallorca B — 66" in layers.viral_formatted_text
        assert "3. SCR Peña Deportiva — 57" in layers.viral_formatted_text
        assert "4. CD Llosetense — 46" in layers.viral_formatted_text
        assert "5." not in layers.viral_formatted_text
        assert "#FutbolBalear #TerceraRFEF" in layers.viral_formatted_text
        assert len(layers.viral_formatted_text) <= 240
    finally:
        session.close()


def test_build_text_layers_produce_viral_ranking() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="segunda_rfef_g3_baleares",
            content_type=ContentType.RANKING,
            priority=70,
            text_draft="RANKINGS DESTACADOS",
            source_summary_hash="hash-ranking-viral",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "2a RFEF con equipos baleares",
                "source_payload": {
                    "best_attack": {"team": "Atletico Baleares", "value": 35},
                    "best_defense": {"team": "UD Poblense", "value": 22},
                    "most_wins": {"team": "UE Sant Andreu", "value": 14},
                },
            },
        )

        layers = service.build_text_layers_for_draft(draft)

        assert layers.viral_formatted_text is not None
        assert layers.viral_formatted_text.startswith("🏆 Ranking")
        assert "1. Atlético Baleares — 35" in layers.viral_formatted_text
        assert "2. UD Poblense — 22" in layers.viral_formatted_text
        assert "3. UE Sant Andreu — 14" in layers.viral_formatted_text
        assert layers.viral_formatted_text.endswith("#FutbolBalear #SegundaRFEF")
        assert len(layers.viral_formatted_text) <= 240
    finally:
        session.close()
