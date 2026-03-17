from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.models import Competition, TeamSocial
from app.services.social_enricher import SocialEnricherService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def build_settings(**overrides) -> Settings:
    payload = {"database_url": "sqlite+pysqlite:///:memory:"}
    payload.update(overrides)
    return Settings(**payload)


def seed_socials(session: Session) -> None:
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
            TeamSocial(
                team_name="CD Manacor",
                competition_slug="tercera_rfef_g11",
                x_handle="@cemanacor",
                followers_approx=15000,
                activity_level="muy_alta",
                is_shared_handle=False,
                is_active=True,
            ),
            TeamSocial(
                team_name="CE Felanitx",
                competition_slug="tercera_rfef_g11",
                x_handle="@cefelanitx",
                followers_approx=5000,
                activity_level="media",
                is_shared_handle=False,
                is_active=True,
            ),
            TeamSocial(
                team_name="RCD Mallorca B",
                competition_slug="tercera_rfef_g11",
                x_handle="@mallorcab",
                followers_approx=30000,
                activity_level="alta",
                is_shared_handle=True,
                is_active=True,
            ),
        ]
    )
    session.commit()


def test_social_enricher_inserts_mentions_into_results_roundup() -> None:
    session = build_session()
    try:
        seed_socials(session)
        service = SocialEnricherService(session, settings=build_settings(max_mentions_per_post=3))

        enriched = service.enrich_text_with_mentions(
            "📋 RESULTADOS\n\n3a RFEF Baleares\nJornada 26\n\nCD Manacor 2-1 CE Felanitx\nRCD Mallorca B 3-0 CE Santanyi\n\n#TerceraRFEF",
            {
                "source_payload": {
                    "matches": [
                        {"home_team": "CD Manacor", "away_team": "CE Felanitx"},
                        {"home_team": "RCD Mallorca B", "away_team": "CE Santanyi"},
                    ]
                }
            },
            "results_roundup",
            competition_slug="tercera_rfef_g11",
        )

        assert "CD Manacor @cemanacor 2-1 CE Felanitx @cefelanitx" in enriched
        assert "RCD Mallorca B @mallorcab 3-0 CE Santanyi" in enriched
    finally:
        session.close()


def test_social_enricher_does_not_duplicate_handles() -> None:
    session = build_session()
    try:
        seed_socials(session)
        service = SocialEnricherService(session, settings=build_settings(max_mentions_per_post=3))

        enriched = service.enrich_text_with_mentions(
            "CD Manacor @cemanacor 2-1 CE Felanitx",
            {
                "source_payload": {
                    "matches": [
                        {"home_team": "CD Manacor", "away_team": "CE Felanitx"},
                    ]
                }
            },
            "results_roundup",
            competition_slug="tercera_rfef_g11",
        )

        assert enriched.count("@cemanacor") == 1
        assert "@cefelanitx" in enriched
    finally:
        session.close()


def test_social_enricher_respects_max_mentions_limit() -> None:
    session = build_session()
    try:
        seed_socials(session)
        service = SocialEnricherService(session, settings=build_settings(max_mentions_per_post=2))

        enriched = service.enrich_text_with_mentions(
            "CD Manacor 2-1 CE Felanitx\nRCD Mallorca B 3-0 CE Santanyi",
            {
                "source_payload": {
                    "matches": [
                        {"home_team": "CD Manacor", "away_team": "CE Felanitx"},
                        {"home_team": "RCD Mallorca B", "away_team": "CE Santanyi"},
                    ]
                }
            },
            "results_roundup",
            competition_slug="tercera_rfef_g11",
        )

        assert enriched.count("@") == 2
    finally:
        session.close()


def test_social_enricher_falls_back_cleanly_when_no_handle_exists() -> None:
    session = build_session()
    try:
        seed_socials(session)
        service = SocialEnricherService(session, settings=build_settings(max_mentions_per_post=3))
        text = "CD Binissalem 1-0 CE Santanyi"

        enriched = service.enrich_text_with_mentions(
            text,
            {
                "source_payload": {
                    "matches": [
                        {"home_team": "CD Binissalem", "away_team": "CE Santanyi"},
                    ]
                }
            },
            "results_roundup",
            competition_slug="tercera_rfef_g11",
        )

        assert enriched == text
    finally:
        session.close()
