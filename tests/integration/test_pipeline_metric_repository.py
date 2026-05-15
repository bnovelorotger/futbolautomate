from __future__ import annotations

from datetime import date, timedelta

import pytest

_models_mod = pytest.importorskip(
    "app.db.models",
    reason="app.db.models not importable",
)
if not hasattr(_models_mod, "PipelineMetric"):
    pytest.skip("PipelineMetric not yet defined in app.db.models", allow_module_level=True)
PipelineMetric = _models_mod.PipelineMetric

_metrics_repo_mod = pytest.importorskip(
    "app.db.repositories.pipeline_metrics",
    reason="PipelineMetricRepository not yet available",
)
PipelineMetricRepository = _metrics_repo_mod.PipelineMetricRepository

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base

TODAY = date(2026, 5, 15)
PIPELINE_A = "test_pipeline_alpha"
PIPELINE_B = "test_pipeline_beta"


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def test_upsert_creates_new_record() -> None:
    session = build_session()
    try:
        repo = PipelineMetricRepository(session)
        repo.upsert(
            TODAY,
            PIPELINE_A,
            candidates_generated=5,
            candidates_approved=3,
            candidates_published=2,
            run_duration_seconds=1.5,
        )
        session.commit()

        rows = session.execute(
            select(PipelineMetric).where(
                PipelineMetric.run_date == TODAY,
                PipelineMetric.pipeline_name == PIPELINE_A,
            )
        ).scalars().all()

        assert len(rows) == 1
        row = rows[0]
        assert row.run_date == TODAY
        assert row.pipeline_name == PIPELINE_A
        assert row.candidates_generated == 5
        assert row.candidates_approved == 3
        assert row.candidates_published == 2
        assert row.run_duration_seconds == 1.5
    finally:
        session.close()


def test_upsert_updates_existing_record() -> None:
    session = build_session()
    try:
        repo = PipelineMetricRepository(session)
        repo.upsert(TODAY, PIPELINE_A, candidates_generated=3)
        session.commit()

        repo.upsert(TODAY, PIPELINE_A, candidates_generated=7, candidates_approved=4)
        session.commit()

        rows = session.execute(
            select(PipelineMetric).where(
                PipelineMetric.run_date == TODAY,
                PipelineMetric.pipeline_name == PIPELINE_A,
            )
        ).scalars().all()

        assert len(rows) == 1
        row = rows[0]
        assert row.candidates_generated == 7
        assert row.candidates_approved == 4
    finally:
        session.close()


def test_upsert_different_pipelines_same_date() -> None:
    session = build_session()
    try:
        repo = PipelineMetricRepository(session)
        repo.upsert(TODAY, PIPELINE_A, candidates_generated=2)
        repo.upsert(TODAY, PIPELINE_B, candidates_generated=8)
        session.commit()

        rows = session.execute(
            select(PipelineMetric).where(PipelineMetric.run_date == TODAY)
        ).scalars().all()

        names = {row.pipeline_name for row in rows}
        assert len(rows) == 2
        assert PIPELINE_A in names
        assert PIPELINE_B in names
    finally:
        session.close()


def test_get_recent_returns_ordered_by_date_desc() -> None:
    session = build_session()
    try:
        repo = PipelineMetricRepository(session)
        date_old = TODAY - timedelta(days=5)
        date_mid = TODAY - timedelta(days=2)
        repo.upsert(date_old, PIPELINE_A)
        repo.upsert(date_mid, PIPELINE_A)
        repo.upsert(TODAY, PIPELINE_A)
        session.commit()

        rows = repo.get_recent(days=30)

        pipeline_rows = [r for r in rows if r.pipeline_name == PIPELINE_A]
        assert len(pipeline_rows) == 3
        assert pipeline_rows[0].run_date == TODAY
        assert pipeline_rows[1].run_date == date_mid
        assert pipeline_rows[2].run_date == date_old
    finally:
        session.close()


def test_get_recent_respects_days_filter() -> None:
    session = build_session()
    try:
        repo = PipelineMetricRepository(session)
        date_old = TODAY - timedelta(days=60)
        repo.upsert(date_old, PIPELINE_A, candidates_generated=1)
        repo.upsert(TODAY, PIPELINE_A, candidates_generated=9)
        session.commit()

        rows = repo.get_recent(days=30)

        pipeline_rows = [r for r in rows if r.pipeline_name == PIPELINE_A]
        assert len(pipeline_rows) == 1
        assert pipeline_rows[0].run_date == TODAY
    finally:
        session.close()


def test_upsert_partial_fields() -> None:
    session = build_session()
    try:
        repo = PipelineMetricRepository(session)
        repo.upsert(TODAY, PIPELINE_A, run_duration_seconds=0.75)
        session.commit()

        row = session.execute(
            select(PipelineMetric).where(
                PipelineMetric.run_date == TODAY,
                PipelineMetric.pipeline_name == PIPELINE_A,
            )
        ).scalars().one()

        assert row.run_duration_seconds == 0.75
        assert row.candidates_generated == 0
        assert row.candidates_approved == 0
        assert row.candidates_autoapproved == 0
        assert row.candidates_rejected == 0
        assert row.candidates_published == 0
        assert row.quality_check_failures == 0
    finally:
        session.close()
