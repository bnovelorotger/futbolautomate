from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import ContentCandidateStatus, ContentType, NarrativeMetricType, ViralStoryType
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
            TeamMention(team_name="CD Manacor", twitter_handle="@cdmanacor", competition_slug="tercera_rfef_g11"),
            TeamMention(team_name="Atletico Baleares", twitter_handle="@atleticbalears", competition_slug="segunda_rfef_g3_baleares"),
        ]
    )
    session.commit()


def test_format_results_summary_uses_new_editorial_title_and_hashtags() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="tercera_rfef_g11",
            content_type=ContentType.RESULTS_ROUNDUP,
            priority=99,
            text_draft="RESULTADOS",
            source_summary_hash="hash-results",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "3a RFEF Baleares",
                "source_payload": {
                    "group_label": "Jornada 26",
                    "matches": [
                        {"home_team": "CD Manacor", "away_team": "RCD Mallorca B", "home_score": 2, "away_score": 1},
                        {"home_team": "CE Felanitx", "away_team": "CD Llosetense", "home_score": 1, "away_score": 1},
                    ],
                },
            },
        )

        formatted = service.apply_to_draft(draft).formatted_text

        assert formatted is not None
        assert formatted.startswith("📋 Resultados - 3ª RFEF - G11 - J26")
        assert "@cdmanacor" not in formatted
        assert formatted.rstrip().endswith("#FutbolBalear #3aRFEF")
    finally:
        session.close()


def test_format_standings_summary_keeps_zone_markers_and_new_title() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="tercera_rfef_g11",
            content_type=ContentType.STANDINGS_ROUNDUP,
            priority=82,
            text_draft="CLASIFICACION",
            source_summary_hash="hash-standings",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "3a RFEF Baleares",
                "source_payload": {
                    "group_label": "Jornada 26",
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
        assert formatted.startswith("📊 Clasificación - 3ª RFEF - G11 - J26")
        assert "[PO]" in formatted
        assert "[DESC]" in formatted
        assert formatted.rstrip().endswith("#FutbolBalear #3aRFEF")
    finally:
        session.close()


def test_format_results_summary_uses_dh_mallorca_title_for_division_honor() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="division_honor_mallorca",
            content_type=ContentType.RESULTS_ROUNDUP,
            priority=88,
            text_draft="RESULTADOS",
            source_summary_hash="hash-results-dh-mallorca",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "Division Honor Mallorca",
                "source_payload": {
                    "group_label": "Jornada 26",
                    "matches": [
                        {"home_team": "CE Andratx B", "away_team": "UD Arenal", "home_score": 2, "away_score": 1},
                        {"home_team": "CD Serverense", "away_team": "UE Collerense", "home_score": 1, "away_score": 1},
                    ],
                },
            },
        )

        formatted = service.apply_to_draft(draft).formatted_text

        assert formatted is not None
        assert formatted.startswith("📋 Resultados - DH Mallorca - J26")
        assert formatted.rstrip().endswith("#FutbolBalear #DH")
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
            text_draft="RESULTADOS",
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
        assert "Inter Ibiza CD 3-0 SD Portmany" not in formatted
    finally:
        session.close()


def test_format_narrative_uses_variant_label_and_hashtags() -> None:
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
                    "story_type": str(ViralStoryType.WIN_STREAK),
                    "team": "CD Manacor",
                    "metric_value": 5,
                },
            },
        )

        formatted = service.apply_to_draft(draft).formatted_text

        assert formatted is not None
        assert formatted.startswith("💪🏼 Forma")
        assert "#FutbolBalear #3aRFEF" in formatted
    finally:
        session.close()


def test_format_narrative_uses_trend_emoji_for_trend_variants() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="tercera_rfef_g11",
            content_type=ContentType.VIRAL_STORY,
            priority=74,
            text_draft="Los partidos de CE Alpha vienen dejando muchos goles en 3a RFEF Baleares.",
            source_summary_hash="hash-trend",
            status=ContentCandidateStatus.DRAFT,
            scheduled_at=datetime(2026, 3, 17, 11, 0, tzinfo=timezone.utc),
            payload_json={
                "competition_name": "3a RFEF Baleares",
                "source_payload": {
                    "story_type": str(ViralStoryType.GOALS_TREND),
                    "team": "CE Alpha",
                    "metric_value": 4.2,
                },
            },
        )

        formatted = service.apply_to_draft(draft).formatted_text

        assert formatted is not None
        assert formatted.startswith("📈 Tendencia")
        assert "#FutbolBalear #3aRFEF" in formatted
    finally:
        session.close()


def test_format_narrative_keeps_fire_emoji_for_data_variants() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="tercera_rfef_g11",
            content_type=ContentType.METRIC_NARRATIVE,
            priority=73,
            text_draft="CD Manacor lidera uno de los apartados estadisticos de 3a RFEF Baleares.",
            source_summary_hash="hash-data",
            status=ContentCandidateStatus.DRAFT,
            scheduled_at=datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc),
            payload_json={
                "competition_name": "3a RFEF Baleares",
                "source_payload": {
                    "narrative_type": str(NarrativeMetricType.BEST_ATTACK),
                    "team": "CD Manacor",
                    "metric_value": 35,
                },
            },
        )

        formatted = service.apply_to_draft(draft).formatted_text

        assert formatted is not None
        assert formatted.startswith("🔥 Dato")
        assert "#FutbolBalear #3aRFEF" in formatted
    finally:
        session.close()


def test_build_text_layers_produce_viral_results_roundup_with_curated_mentions() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="segunda_rfef_g3_baleares",
            content_type=ContentType.RESULTS_ROUNDUP,
            priority=99,
            text_draft="RESULTADOS",
            source_summary_hash="hash-results-viral",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "2a RFEF con equipos baleares",
                "source_payload": {
                    "group_label": "Jornada 27",
                    "matches": [
                        {"home_team": "Atletico Baleares", "away_team": "UE Porreres", "home_score": 2, "away_score": 0},
                        {"home_team": "UD Poblense", "away_team": "Torrent CF", "home_score": 1, "away_score": 1},
                    ],
                },
            },
        )

        layers = service.build_text_layers_for_draft(draft)

        assert layers.viral_formatted_text is not None
        assert layers.viral_formatted_text.startswith("📋 Resultados - 2ª RFEF - G3 - J27")
        assert "@atleticbalears 2-0 UE Porreres" in layers.viral_formatted_text
        assert layers.viral_formatted_text.endswith("#FutbolBalear #2aRFEF")
    finally:
        session.close()


def test_build_text_layers_produce_viral_preview_with_key_match_mentions() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="segunda_rfef_g3_baleares",
            content_type=ContentType.PREVIEW,
            priority=90,
            text_draft="PREVIA",
            source_summary_hash="hash-preview-viral",
            status=ContentCandidateStatus.DRAFT,
            payload_json={
                "competition_name": "2a RFEF con equipos baleares",
                "source_payload": {
                    "featured_match": {"round_name": "Jornada 28", "home_team": "Atletico Baleares", "away_team": "UD Poblense"},
                    "matches": [
                        {"round_name": "Jornada 28", "home_team": "Atletico Baleares", "away_team": "UD Poblense"},
                        {"round_name": "Jornada 28", "home_team": "UE Sant Andreu", "away_team": "UE Olot"},
                    ],
                },
            },
        )

        layers = service.build_text_layers_for_draft(draft)

        assert layers.viral_formatted_text is not None
        assert layers.viral_formatted_text.startswith("🔎 Previa - 2ª RFEF - G3 - J28")
        assert "Partido clave:" in layers.viral_formatted_text
        assert "@atleticbalears" in layers.viral_formatted_text
        assert layers.viral_formatted_text.endswith("#FutbolBalear #2aRFEF")
    finally:
        session.close()


def test_build_text_layers_produce_viral_ranking_with_metric_title() -> None:
    session = build_session()
    try:
        seed_catalog(session)
        service = EditorialFormatterService(session)
        draft = ContentCandidateDraft(
            competition_slug="segunda_rfef_g3_baleares",
            content_type=ContentType.RANKING,
            priority=70,
            text_draft="RANKINGS",
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
        assert layers.viral_formatted_text.startswith("🏆 Mejor ataque - 2ª RFEF - G3")
        assert "Mejor ataque: @atleticbalears - 35" in layers.viral_formatted_text
        assert "Más sólida atrás: UD Poblense - 22" in layers.viral_formatted_text
        assert layers.viral_formatted_text.endswith("#FutbolBalear #2aRFEF")
    finally:
        session.close()
