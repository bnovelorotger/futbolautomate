from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import News
from app.services.news_editorial import enrich_news_editorial
from app.services.news_editorial_queries import NewsEditorialQueryService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def seed_news(session: Session) -> None:
    session.add_all(
        [
            News(
                source_name="ultima_hora",
                source_url="https://example.com/mallorca-espanyol",
                title="Horario y donde ver el Real Mallorca - RCD Espanyol",
                subtitle=None,
                published_at=datetime(2026, 3, 13, 15, 38, tzinfo=timezone.utc),
                summary="Partido de LaLiga en Son Moix.",
                body_text=None,
                news_type="other",
                clubs_detected=[],
                competition_detected=None,
                raw_category="Deportes | Real Mallorca",
                scraped_at=datetime(2026, 3, 13, 16, 0, tzinfo=timezone.utc),
                content_hash="news-1",
            ),
            News(
                source_name="diario_mallorca",
                source_url="https://example.com/llosetense",
                title="El Llosetense de Tercera busca en Eivissa su cuarto triunfo seguido",
                subtitle=None,
                published_at=datetime(2026, 3, 14, 6, 1, 9, tzinfo=timezone.utc),
                summary="La 3a RFEF Baleares entra en una jornada clave.",
                body_text=None,
                news_type="other",
                clubs_detected=[],
                competition_detected=None,
                raw_category="Deportes",
                scraped_at=datetime(2026, 3, 14, 6, 10, tzinfo=timezone.utc),
                content_hash="news-2",
            ),
            News(
                source_name="ultima_hora",
                source_url="https://example.com/real-madrid",
                title="El Real Madrid prepara el derbi ante el Atletico",
                subtitle=None,
                published_at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
                summary="Partido de LaLiga en Madrid.",
                body_text=None,
                news_type="other",
                clubs_detected=[],
                competition_detected=None,
                raw_category="Deportes",
                scraped_at=datetime(2026, 3, 13, 12, 5, tzinfo=timezone.utc),
                content_hash="news-3",
            ),
            News(
                source_name="ultima_hora",
                source_url="https://example.com/palma-futsal",
                title="El Palma Futsal retoma la liga",
                subtitle=None,
                published_at=datetime(2026, 3, 13, 16, 2, tzinfo=timezone.utc),
                summary="El equipo disputa la LNFS tras la Final Four de la UEFA Futsal Champions League.",
                body_text=None,
                news_type="other",
                clubs_detected=[],
                competition_detected=None,
                raw_category="Deportes | Palma Futsal",
                scraped_at=datetime(2026, 3, 13, 16, 10, tzinfo=timezone.utc),
                content_hash="news-4",
            ),
        ]
    )
    session.commit()


def test_news_editorial_enrichment_and_queries() -> None:
    session = build_session()
    try:
        seed_news(session)

        initial_stats = enrich_news_editorial(session)
        session.commit()
        repeated_stats = enrich_news_editorial(session)
        session.commit()

        service = NewsEditorialQueryService(session)
        relevant = service.relevant_balearic_football(limit=10)
        non_balearic = service.football_non_balearic(limit=10)
        real_mallorca = service.by_club("Real Mallorca", limit=10)
        tercera = service.by_competition("3a RFEF Grupo 11", limit=10)
        top = service.top_scores(limit=2)
        summary = service.summary_counts()

        assert initial_stats.found == 4
        assert initial_stats.inserted == 4
        assert initial_stats.updated == 0
        assert repeated_stats.inserted == 0
        assert repeated_stats.updated == 0

        assert len(relevant) == 2
        assert any("Real Mallorca" in (item.clubs_detected or []) for item in relevant)
        assert len(non_balearic) == 1
        assert non_balearic[0].title == "El Real Madrid prepara el derbi ante el Atletico"
        assert len(real_mallorca) == 1
        assert len(tercera) == 1
        assert top[0].editorial_relevance_score >= top[1].editorial_relevance_score
        assert summary.relevant_balearic_football == 2
        assert summary.football_non_balearic == 1
        assert summary.other_sports_or_unknown == 1
    finally:
        session.close()
