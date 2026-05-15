"""Integration tests for the metrics hook in the editorial_release CLI.

The metric write now lives in `app.pipelines.editorial_release.run`, so these
tests exercise the command entrypoint with an in-memory DB and a patched
session scope.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date as date_type
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

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

from app.db.base import Base
from app.pipelines import editorial_release as editorial_release_cli
from tests.unit.services.test_editorial_release_pipeline import (
    build_release_service,
    seed_release_candidates,
)

REFERENCE_DATE = date_type(2026, 3, 17)


def _build_session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _metric_rows(session: Session, pipeline_name: str) -> list:
    return list(
        session.execute(
            select(PipelineMetric).where(PipelineMetric.pipeline_name == pipeline_name)
        )
        .scalars()
        .all()
    )


def _session_scope(factory):
    @contextmanager
    def _scope():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _scope


def _run_release_cli(factory, tmp_path: Path) -> None:
    with patch.object(editorial_release_cli, "init_db", lambda: None):
        with patch.object(editorial_release_cli, "set_run_id", lambda: None):
            with patch.object(editorial_release_cli, "session_scope", _session_scope(factory)):
                with patch.object(
                    editorial_release_cli,
                    "EditorialReleasePipelineService",
                    lambda session: build_release_service(session, tmp_path),
                ):
                    with patch.object(editorial_release_cli.typer, "echo", lambda *args, **kwargs: None):
                        editorial_release_cli.run(
                            reference_date=REFERENCE_DATE.isoformat(),
                            limit=200,
                            use_draft=False,
                            use_rewrite=False,
                            publish_x=False,
                            as_json=False,
                        )


def test_metrics_recorded_after_successful_release(tmp_path: Path) -> None:
    factory = _build_session_factory()
    seed_session = factory()
    verify_session: Session | None = None
    try:
        seed_release_candidates(seed_session)
        seed_session.close()

        _run_release_cli(factory, tmp_path)

        verify_session = factory()
        rows = _metric_rows(verify_session, "editorial_release")

        assert len(rows) == 1, "Expected exactly one PipelineMetric row for editorial_release"
        metric = rows[0]
        assert metric.pipeline_name == "editorial_release"
        assert metric.run_duration_seconds is not None
        assert metric.run_duration_seconds > 0, (
            f"run_duration_seconds must be positive, got {metric.run_duration_seconds}"
        )
    finally:
        if verify_session is not None:
            verify_session.close()


def test_metrics_hook_does_not_raise_on_db_failure(tmp_path: Path) -> None:
    seed_session = None
    factory = _build_session_factory()
    try:
        seed_session = factory()
        seed_release_candidates(seed_session)
        seed_session.close()

        with patch.object(
            PipelineMetricRepository,
            "upsert",
            side_effect=RuntimeError("simulated metrics DB failure"),
        ):
            _run_release_cli(factory, tmp_path)
    finally:
        if seed_session is not None:
            seed_session.close()


def test_metrics_upsert_updates_existing_row(tmp_path: Path) -> None:
    factory = _build_session_factory()
    seed_session = factory()
    verify_session: Session | None = None
    try:
        seed_release_candidates(seed_session)
        seed_session.close()

        _run_release_cli(factory, tmp_path)

        verify_session = factory()
        rows_after_first = _metric_rows(verify_session, "editorial_release")
        assert len(rows_after_first) == 1, "Expected one metric row after the first run"
        verify_session.close()
        verify_session = None

        _run_release_cli(factory, tmp_path)

        verify_session = factory()
        rows_after_second = _metric_rows(verify_session, "editorial_release")
        assert len(rows_after_second) == 1, (
            "Expected still only one PipelineMetric row after the second run "
            f"(upsert semantics), but found {len(rows_after_second)}"
        )
    finally:
        if verify_session is not None:
            verify_session.close()
