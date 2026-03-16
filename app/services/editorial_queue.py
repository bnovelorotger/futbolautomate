from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.schemas.editorial_queue import (
    EditorialQueueCandidateDetail,
    EditorialQueueCandidateView,
    EditorialQueueSummary,
)
from app.utils.time import utcnow


ALLOWED_STATUS_TRANSITIONS: dict[ContentCandidateStatus, set[ContentCandidateStatus]] = {
    ContentCandidateStatus.DRAFT: {
        ContentCandidateStatus.APPROVED,
        ContentCandidateStatus.REJECTED,
    },
    ContentCandidateStatus.APPROVED: {
        ContentCandidateStatus.DRAFT,
        ContentCandidateStatus.REJECTED,
        ContentCandidateStatus.PUBLISHED,
    },
    ContentCandidateStatus.REJECTED: {
        ContentCandidateStatus.DRAFT,
    },
    ContentCandidateStatus.PUBLISHED: set(),
}


def _excerpt(text: str, limit: int = 90) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


class EditorialQueueService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ContentCandidateRepository(session)

    def _candidate(self, candidate_id: int) -> ContentCandidate:
        candidate = self.repository.get(candidate_id)
        if candidate is None:
            raise ConfigurationError(f"Content candidate desconocido: {candidate_id}")
        return candidate

    def _validate_transition(
        self,
        current_status: ContentCandidateStatus,
        next_status: ContentCandidateStatus,
    ) -> None:
        if next_status == current_status:
            return
        if next_status not in ALLOWED_STATUS_TRANSITIONS[current_status]:
            raise InvalidStateTransitionError(
                f"Transicion no permitida: {current_status} -> {next_status}"
            )

    def _row_to_view(self, row: ContentCandidate) -> EditorialQueueCandidateView:
        return EditorialQueueCandidateView(
            id=row.id,
            competition_slug=row.competition_slug,
            content_type=ContentType(row.content_type),
            priority=row.priority,
            status=ContentCandidateStatus(row.status),
            scheduled_at=row.scheduled_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            reviewed_at=row.reviewed_at,
            excerpt=_excerpt(row.text_draft),
        )

    def _row_to_detail(self, row: ContentCandidate) -> EditorialQueueCandidateDetail:
        return EditorialQueueCandidateDetail(
            id=row.id,
            competition_slug=row.competition_slug,
            content_type=ContentType(row.content_type),
            priority=row.priority,
            status=ContentCandidateStatus(row.status),
            text_draft=row.text_draft,
            payload_json=row.payload_json or {},
            source_summary_hash=row.source_summary_hash,
            scheduled_at=row.scheduled_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            reviewed_at=row.reviewed_at,
            approved_at=row.approved_at,
            published_at=row.published_at,
            rejection_reason=row.rejection_reason,
        )

    def list_candidates(
        self,
        status: ContentCandidateStatus | None = None,
        competition_slug: str | None = None,
        content_type: ContentType | None = None,
        priority_min: int | None = None,
        limit: int = 50,
    ) -> list[EditorialQueueCandidateView]:
        query = select(ContentCandidate)
        if status is not None:
            query = query.where(ContentCandidate.status == str(status))
        if competition_slug is not None:
            query = query.where(ContentCandidate.competition_slug == competition_slug)
        if content_type is not None:
            query = query.where(ContentCandidate.content_type == str(content_type))
        if priority_min is not None:
            query = query.where(ContentCandidate.priority >= priority_min)
        query = query.order_by(
            ContentCandidate.priority.desc(),
            ContentCandidate.created_at.desc(),
            ContentCandidate.id.desc(),
        ).limit(limit)
        rows = self.session.execute(query).scalars().all()
        return [self._row_to_view(row) for row in rows]

    def get_candidate(self, candidate_id: int) -> EditorialQueueCandidateDetail:
        return self._row_to_detail(self._candidate(candidate_id))

    def approve_candidate(self, candidate_id: int) -> EditorialQueueCandidateDetail:
        candidate = self._candidate(candidate_id)
        current_status = ContentCandidateStatus(candidate.status)
        self._validate_transition(current_status, ContentCandidateStatus.APPROVED)
        timestamp = utcnow()
        candidate.status = str(ContentCandidateStatus.APPROVED)
        candidate.reviewed_at = timestamp
        candidate.approved_at = timestamp
        candidate.published_at = None
        candidate.rejection_reason = None
        self.session.add(candidate)
        self.session.flush()
        return self._row_to_detail(candidate)

    def reject_candidate(
        self,
        candidate_id: int,
        rejection_reason: str | None = None,
    ) -> EditorialQueueCandidateDetail:
        candidate = self._candidate(candidate_id)
        current_status = ContentCandidateStatus(candidate.status)
        self._validate_transition(current_status, ContentCandidateStatus.REJECTED)
        candidate.status = str(ContentCandidateStatus.REJECTED)
        candidate.reviewed_at = utcnow()
        candidate.approved_at = None
        candidate.published_at = None
        candidate.rejection_reason = rejection_reason
        self.session.add(candidate)
        self.session.flush()
        return self._row_to_detail(candidate)

    def reset_candidate(self, candidate_id: int) -> EditorialQueueCandidateDetail:
        candidate = self._candidate(candidate_id)
        current_status = ContentCandidateStatus(candidate.status)
        self._validate_transition(current_status, ContentCandidateStatus.DRAFT)
        candidate.status = str(ContentCandidateStatus.DRAFT)
        candidate.reviewed_at = utcnow()
        candidate.approved_at = None
        candidate.published_at = None
        candidate.rejection_reason = None
        self.session.add(candidate)
        self.session.flush()
        return self._row_to_detail(candidate)

    def publish_candidate(self, candidate_id: int) -> EditorialQueueCandidateDetail:
        candidate = self._candidate(candidate_id)
        current_status = ContentCandidateStatus(candidate.status)
        self._validate_transition(current_status, ContentCandidateStatus.PUBLISHED)
        timestamp = utcnow()
        candidate.status = str(ContentCandidateStatus.PUBLISHED)
        candidate.reviewed_at = timestamp
        candidate.published_at = timestamp
        candidate.rejection_reason = None
        self.session.add(candidate)
        self.session.flush()
        return self._row_to_detail(candidate)

    def schedule_candidate(
        self,
        candidate_id: int,
        scheduled_at: datetime,
    ) -> EditorialQueueCandidateDetail:
        candidate = self._candidate(candidate_id)
        current_status = ContentCandidateStatus(candidate.status)
        if current_status not in {ContentCandidateStatus.DRAFT, ContentCandidateStatus.APPROVED}:
            raise InvalidStateTransitionError(
                f"No se puede programar un candidato en estado {current_status}"
            )
        candidate.scheduled_at = scheduled_at
        self.session.add(candidate)
        self.session.flush()
        return self._row_to_detail(candidate)

    def summary(self) -> EditorialQueueSummary:
        rows: Sequence[tuple[str, int]] = self.session.execute(
            select(ContentCandidate.status, func.count())
            .group_by(ContentCandidate.status)
            .order_by(ContentCandidate.status)
        ).all()
        counts = {status: count for status, count in rows}
        scheduled_pending = self.session.scalar(
            select(func.count())
            .select_from(ContentCandidate)
            .where(
                ContentCandidate.scheduled_at.is_not(None),
                ContentCandidate.status.in_(
                    [
                        str(ContentCandidateStatus.DRAFT),
                        str(ContentCandidateStatus.APPROVED),
                    ]
                ),
            )
        ) or 0
        return EditorialQueueSummary(
            total_drafts=counts.get(str(ContentCandidateStatus.DRAFT), 0),
            total_approved=counts.get(str(ContentCandidateStatus.APPROVED), 0),
            total_rejected=counts.get(str(ContentCandidateStatus.REJECTED), 0),
            total_published=counts.get(str(ContentCandidateStatus.PUBLISHED), 0),
            total_scheduled_pending=scheduled_pending,
        )
