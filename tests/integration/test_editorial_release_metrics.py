"""Integration tests for the metrics hook in EditorialReleasePipelineService.

The pipeline records a PipelineMetric row after each run via a try/except hook,
so a DB write failure must never break the main release flow.

These tests cover:
  1. A metric row is written after a successful run.
  2. A DB failure in the upsert does not propagate to the caller.
  3. A second run on the same day upserts (one row, not two).

All three tests use SQLite in-memory and the same session/seeding helpers as the
existing unit tests for EditorialReleasePipelineService.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Guard: skip the whole module if the metrics infrastructure does not exist yet.
# Remove the two blocks below (and simplify to plain imports) once
# PipelineMetric + PipelineMetricRepository are merged to main.
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Standard imports (only reached when the guard above succeeds)
# ---------------------------------------------------------------------------

from datetime import date as date_type
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from tests.unit.services.test_editorial_release_pipeline import (
    build_release_service,
    seed_release_candidates,
)

REFERENCE_DATE = date_type(2026, 3, 17)


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

def _build_session() -> Session:
    """Return a fresh SQLite in-memory session with all tables created."""
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


# ---------------------------------------------------------------------------
# Helper: count PipelineMetric rows for a given pipeline_name
# ---------------------------------------------------------------------------

def _metric_rows(session: Session, pipeline_name: str) -> list:
    return list(
        session.execute(
            select(PipelineMetric).where(PipelineMetric.pipeline_name == pipeline_name)
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# Test 1: A metric row is persisted after a successful run
# ---------------------------------------------------------------------------

def test_metrics_recorded_after_successful_release(tmp_path: Path) -> None:
    """After a real (non-dry) run the pipeline must write one PipelineMetric row
    with pipeline_name='editorial_release' and run_duration_seconds > 0.
    """
    session = _build_session()
    try:
        seed_release_candidates(session)
        service = build_release_service(session, tmp_path)

        service.run(reference_date=REFERENCE_DATE, dry_run=False)
        session.commit()

        rows = _metric_rows(session, "editorial_release")

        assert len(rows) == 1, "Expected exactly one PipelineMetric row for editorial_release"
        metric = rows[0]
        assert metric.pipeline_name == "editorial_release"
        assert metric.run_duration_seconds is not None
        assert metric.run_duration_seconds > 0, (
            f"run_duration_seconds must be positive, got {metric.run_duration_seconds}"
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Test 2: A DB failure in the upsert must not propagate to the caller
# ---------------------------------------------------------------------------

def test_metrics_hook_does_not_raise_on_db_failure(tmp_path: Path) -> None:
    """If PipelineMetricRepository.upsert raises an exception the pipeline must
    still complete successfully — the try/except around the metrics hook must
    swallow the error and return the normal EditorialReleaseResult.
    """
    session = _build_session()
    try:
        seed_release_candidates(session)
        service = build_release_service(session, tmp_path)

        with patch.object(
            PipelineMetricRepository,
            "upsert",
            side_effect=RuntimeError("simulated metrics DB failure"),
        ):
            # Must NOT raise — the try/except in the hook protects the main flow.
            result = service.run(reference_date=REFERENCE_DATE, dry_run=False)
            session.commit()

        # The pipeline still returned a valid result.
        assert result is not None
        assert result.autoapproved_count >= 0
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Test 3: A second run on the same day upserts (single row, not two)
# ---------------------------------------------------------------------------

def test_metrics_upsert_updates_existing_row(tmp_path: Path) -> None:
    """Running the pipeline twice on the same day must result in exactly one
    PipelineMetric row — the second run upserts, not inserts a duplicate.
    """
    session = _build_session()
    try:
        seed_release_candidates(session)
        service = build_release_service(session, tmp_path)

        # First run — creates the row.
        service.run(reference_date=REFERENCE_DATE, dry_run=False)
        session.commit()

        rows_after_first = _metric_rows(session, "editorial_release")
        assert len(rows_after_first) == 1, "Expected one metric row after the first run"

        # Second run — must upsert the existing row, not insert a new one.
        service.run(reference_date=REFERENCE_DATE, dry_run=False)
        session.commit()

        rows_after_second = _metric_rows(session, "editorial_release")
        assert len(rows_after_second) == 1, (
            "Expected still only one PipelineMetric row after the second run "
            f"(upsert semantics), but found {len(rows_after_second)}"
        )
    finally:
        session.close()
