from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import InvalidStateTransitionError
from app.db.base import Base
from app.db.models import Competition, ContentCandidate
from app.services.publication_dispatcher import PublicationDispatcherService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def seed_candidates(session: Session) -> None:
    base_time = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)
    competition = Competition(
        code="segunda_rfef_g3_baleares",
        name="2a RFEF Grupo 3",
        normalized_name="2a rfef grupo 3",
        category_level=4,
        gender="male",
        region="Baleares",
        country="Spain",
        federation="RFEF",
        source_name="futbolme",
        source_competition_id="3059",
    )
    session.add(competition)
    session.flush()
    session.add_all(
        [
            ContentCandidate(
                competition_slug="segunda_rfef_g3_baleares",
                content_type="match_result",
                priority=95,
                text_draft="RESULTADO FINAL\n\nA",
                payload_json={"content_key": "a"},
                source_summary_hash="hash-a",
                scheduled_at=datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc),
                status="approved",
                reviewed_at=base_time,
                approved_at=base_time,
                published_at=None,
                rejection_reason=None,
                external_publication_ref=None,
                created_at=datetime(2026, 3, 14, 8, 0, tzinfo=timezone.utc),
                updated_at=base_time,
            ),
            ContentCandidate(
                competition_slug="segunda_rfef_g3_baleares",
                content_type="preview",
                priority=99,
                text_draft="PREVIA DE LA JORNADA\n\nB",
                payload_json={"content_key": "b"},
                source_summary_hash="hash-b",
                scheduled_at=datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc),
                status="approved",
                reviewed_at=base_time,
                approved_at=base_time,
                published_at=None,
                rejection_reason=None,
                external_publication_ref=None,
                created_at=datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc),
                updated_at=base_time,
            ),
            ContentCandidate(
                competition_slug="segunda_rfef_g3_baleares",
                content_type="standings",
                priority=80,
                text_draft="CLASIFICACION\n\nC",
                payload_json={"content_key": "c"},
                source_summary_hash="hash-c",
                scheduled_at=None,
                status="approved",
                reviewed_at=base_time,
                approved_at=base_time,
                published_at=None,
                rejection_reason=None,
                external_publication_ref=None,
                created_at=datetime(2026, 3, 14, 7, 0, tzinfo=timezone.utc),
                updated_at=base_time,
            ),
            ContentCandidate(
                competition_slug="segunda_rfef_g3_baleares",
                content_type="ranking",
                priority=90,
                text_draft="RANKING\n\nD",
                payload_json={"content_key": "d"},
                source_summary_hash="hash-d",
                scheduled_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
                status="approved",
                reviewed_at=base_time,
                approved_at=base_time,
                published_at=None,
                rejection_reason=None,
                external_publication_ref=None,
                created_at=datetime(2026, 3, 14, 6, 0, tzinfo=timezone.utc),
                updated_at=base_time,
            ),
            ContentCandidate(
                competition_slug="segunda_rfef_g3_baleares",
                content_type="stat_narrative",
                priority=70,
                text_draft="NARRATIVA\n\nE",
                payload_json={"content_key": "e"},
                source_summary_hash="hash-e",
                scheduled_at=datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc),
                status="draft",
                reviewed_at=None,
                approved_at=None,
                published_at=None,
                rejection_reason=None,
                external_publication_ref=None,
                created_at=datetime(2026, 3, 14, 5, 0, tzinfo=timezone.utc),
                updated_at=base_time,
            ),
            ContentCandidate(
                competition_slug="segunda_rfef_g3_baleares",
                content_type="match_result",
                priority=60,
                text_draft="RESULTADO FINAL\n\nF",
                payload_json={"content_key": "f"},
                source_summary_hash="hash-f",
                scheduled_at=datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc),
                status="rejected",
                reviewed_at=base_time,
                approved_at=None,
                published_at=None,
                rejection_reason="duplicado",
                external_publication_ref=None,
                created_at=datetime(2026, 3, 14, 4, 0, tzinfo=timezone.utc),
                updated_at=base_time,
            ),
        ]
    )
    session.commit()


def test_publication_dispatcher_lists_ready_and_summarizes() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        service = PublicationDispatcherService(session)
        now = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)

        ready = service.list_ready(now=now, include_unscheduled=True)
        summary = service.summary(now=now)

        assert [row.id for row in ready] == [2, 1, 3]
        assert summary.total_ready == 3
        assert summary.total_approved_future == 1
        assert summary.total_published == 0
        assert summary.total_rejected == 1
        assert summary.total_drafts == 1
    finally:
        session.close()


def test_publication_dispatcher_dry_run_and_dispatch() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        service = PublicationDispatcherService(session)
        now = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)

        dry_run = service.dispatch(now=now, limit=10, dry_run=True, include_unscheduled=False)
        assert dry_run.dry_run is True
        assert [row.id for row in dry_run.rows] == [2, 1]
        assert service.summary(now=now).total_published == 0

        dispatched = service.dispatch(now=now, limit=10, dry_run=False, include_unscheduled=False)
        session.commit()

        assert dispatched.dry_run is False
        assert [row.id for row in dispatched.rows] == [2, 1]
        assert all(row.status == "published" for row in dispatched.rows)
        assert service.summary(now=now).total_published == 2
        assert service.summary(now=now).total_approved_future == 1
    finally:
        session.close()


def test_publication_dispatcher_dispatch_candidates_respects_future_schedule_when_requested() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        service = PublicationDispatcherService(session)
        now = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)

        dispatched = service.dispatch_candidates(
            [1, 2, 3, 4],
            published_at=now,
            only_ready=True,
            include_unscheduled=True,
            dry_run=False,
        )
        session.commit()

        assert [row.id for row in dispatched.rows] == [2, 1, 3]
        assert session.get(ContentCandidate, 4).status == "approved"
        assert session.get(ContentCandidate, 4).published_at is None
    finally:
        session.close()


def test_publication_dispatcher_publish_by_id_validates_state() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        service = PublicationDispatcherService(session)
        now = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)

        published = service.publish_candidate(4, published_at=now, external_publication_ref="manual-4")
        session.commit()

        assert published.status == "published"
        assert published.published_at == now

        with pytest.raises(InvalidStateTransitionError):
            service.publish_candidate(5, published_at=now)

        with pytest.raises(InvalidStateTransitionError):
            service.publish_candidate(6, published_at=now)

        with pytest.raises(InvalidStateTransitionError):
            service.publish_candidate(4, published_at=now)
    finally:
        session.close()
