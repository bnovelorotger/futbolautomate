from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import SourceName
from app.db.base import Base
from app.scrapers.media.rss import RSSParser
from app.services.ingest_news import ingest_news
from app.services.news_queries import NewsQueryService
from tests.helpers import read_fixture


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def test_news_ingest_is_idempotent_and_queryable() -> None:
    session = build_session()
    try:
        parser = RSSParser()
        diario_records = parser.parse(
            read_fixture("diario_mallorca_rss.xml"),
            source_name=SourceName.DIARIO_MALLORCA,
        )
        ultima_records = parser.parse(
            read_fixture("ultima_hora_atom.xml"),
            source_name=SourceName.ULTIMA_HORA,
        )

        initial_stats = ingest_news(session, diario_records + ultima_records)
        session.commit()

        repeated_stats = ingest_news(session, diario_records + ultima_records)
        session.commit()

        duplicate_hash_record = diario_records[0].model_copy(
            update={"source_url": "https://www.diariodemallorca.es/deportes/2026/03/14/atletico-baleares-vuelve-liderato-duplicada.html"}
        )
        duplicate_hash_stats = ingest_news(session, [duplicate_hash_record])
        session.commit()

        service = NewsQueryService(session)
        latest = service.latest(limit=4)
        today = service.today(limit=10, reference_date=date(2026, 3, 14))
        by_source = service.by_source(SourceName.ULTIMA_HORA, limit=5)
        search = service.search_titles("mallorca", limit=10)

        assert initial_stats.found == 4
        assert initial_stats.inserted == 4
        assert initial_stats.updated == 0
        assert repeated_stats.inserted == 0
        assert repeated_stats.updated == 0
        assert duplicate_hash_stats.inserted == 0
        assert duplicate_hash_stats.updated == 0

        assert len(latest) == 4
        assert latest[0].source_name == "diario_mallorca"
        assert any(item.news_type == "preview" for item in latest)
        assert len(today) == 2
        assert {item.source_name for item in today} == {"diario_mallorca"}
        assert len(by_source) == 2
        assert all(item.source_name == "ultima_hora" for item in by_source)
        assert len(search) >= 2
        assert any("Mallorca" in item.title for item in search)
    finally:
        session.close()
