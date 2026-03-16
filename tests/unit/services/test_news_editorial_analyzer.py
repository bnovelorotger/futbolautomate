from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import News, Team
from app.services.news_editorial import NewsEditorialAnalyzer


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def test_news_editorial_analyzer_detects_balearic_football_relevance() -> None:
    session = build_session()
    try:
        session.add(Team(name="CE Andratx", normalized_name="ce andratx", gender="male"))
        session.flush()
        news = News(
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
        )
        session.add(news)
        session.flush()

        result = NewsEditorialAnalyzer(session).analyze(news)

        assert result.sport_detected == "football"
        assert result.is_football is True
        assert result.is_balearic_related is True
        assert "Real Mallorca" in result.clubs_detected
        assert result.editorial_relevance_score > 10
    finally:
        session.close()


def test_news_editorial_analyzer_separates_non_football_balearic_news() -> None:
    session = build_session()
    try:
        news = News(
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
            content_hash="news-2",
        )
        session.add(news)
        session.flush()

        result = NewsEditorialAnalyzer(session).analyze(news)

        assert result.sport_detected == "futsal"
        assert result.is_football is False
        assert result.is_balearic_related is True
        assert result.editorial_relevance_score < 0
    finally:
        session.close()


def test_news_editorial_analyzer_detects_football_non_balearic() -> None:
    session = build_session()
    try:
        news = News(
            source_name="diario_mallorca",
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
        )
        session.add(news)
        session.flush()

        result = NewsEditorialAnalyzer(session).analyze(news)

        assert result.sport_detected == "football"
        assert result.is_football is True
        assert result.is_balearic_related is False
        assert result.editorial_relevance_score > 0
    finally:
        session.close()
