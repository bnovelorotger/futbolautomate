from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.services.competition_catalog_service import CompetitionCatalogService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def test_competition_catalog_service_detects_missing_integrated_competitions_and_seeds_them() -> None:
    session = build_session()
    try:
        service = CompetitionCatalogService(session)

        initial = service.status(integrated_only=True)
        result = service.seed_competitions(integrated_only=True, missing_only=True)
        final = service.status(integrated_only=True)

        assert len(initial) == 7
        assert all(row.seeded_in_db is False for row in initial)
        assert result.seeded_count == 7
        assert result.updated_count == 0
        assert result.skipped_count == 0
        assert all(row.seeded_in_db is True for row in final)
    finally:
        session.close()
