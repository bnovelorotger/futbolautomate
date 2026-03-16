from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import ContentCandidateStatus
from app.core.exceptions import InvalidStateTransitionError
from app.db.base import Base
from app.db.models import Competition, ContentCandidate
from app.services.editorial_queue import EditorialQueueService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def seed_candidates(session: Session) -> None:
    now = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)
    competition = Competition(
        code="tercera_rfef_g11",
        name="3a RFEF Grupo 11",
        normalized_name="3a rfef grupo 11",
        category_level=5,
        gender="male",
        region="Baleares",
        country="Spain",
        federation="RFEF",
        source_name="futbolme",
        source_competition_id="3065",
    )
    session.add(competition)
    session.flush()
    session.add_all(
        [
            ContentCandidate(
                competition_slug="tercera_rfef_g11",
                content_type="match_result",
                priority=99,
                text_draft="RESULTADO FINAL\n\nCD Llosetense 3-0 SD Portmany",
                payload_json={"content_key": "result:1"},
                source_summary_hash="hash-1",
                scheduled_at=None,
                status="draft",
                reviewed_at=None,
                approved_at=None,
                published_at=None,
                rejection_reason=None,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                competition_slug="tercera_rfef_g11",
                content_type="preview",
                priority=90,
                text_draft="PREVIA DE LA JORNADA\n\nPartido destacado",
                payload_json={"content_key": "preview:1"},
                source_summary_hash="hash-2",
                scheduled_at=now,
                status="approved",
                reviewed_at=now,
                approved_at=now,
                published_at=None,
                rejection_reason=None,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                competition_slug="tercera_rfef_g11",
                content_type="ranking",
                priority=70,
                text_draft="RANKINGS DESTACADOS\n\nMejor ataque",
                payload_json={"content_key": "ranking:1"},
                source_summary_hash="hash-3",
                scheduled_at=None,
                status="rejected",
                reviewed_at=now,
                approved_at=None,
                published_at=None,
                rejection_reason="duplicado",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()


def test_editorial_queue_service_lists_filters_and_summarizes() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        service = EditorialQueueService(session)

        drafts = service.list_candidates(status=ContentCandidateStatus.DRAFT)
        previews = service.list_candidates(content_type="preview")
        priority_rows = service.list_candidates(priority_min=80)
        summary = service.summary()

        assert len(drafts) == 1
        assert drafts[0].content_type == "match_result"
        assert len(previews) == 1
        assert previews[0].status == "approved"
        assert len(priority_rows) == 2
        assert summary.total_drafts == 1
        assert summary.total_approved == 1
        assert summary.total_rejected == 1
        assert summary.total_published == 0
        assert summary.total_scheduled_pending == 1
    finally:
        session.close()


def test_editorial_queue_service_supports_review_flow_and_schedule() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        service = EditorialQueueService(session)
        scheduled_at = datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)

        approved = service.approve_candidate(1)
        scheduled = service.schedule_candidate(1, scheduled_at)
        rejected = service.reject_candidate(2, rejection_reason="se queda fuera")
        reset = service.reset_candidate(3)
        published = service.publish_candidate(1)
        session.commit()

        assert approved.status == "approved"
        assert approved.approved_at is not None
        assert scheduled.scheduled_at == scheduled_at
        assert rejected.status == "rejected"
        assert rejected.rejection_reason == "se queda fuera"
        assert reset.status == "draft"
        assert reset.rejection_reason is None
        assert published.status == "published"
        assert published.published_at is not None

        with pytest.raises(InvalidStateTransitionError):
            service.schedule_candidate(2, scheduled_at)
    finally:
        session.close()
