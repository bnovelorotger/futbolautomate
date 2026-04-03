from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.schemas.publication_dispatch import (
    PublicationCandidateView,
    PublicationDispatchResult,
    PublicationDispatchSummary,
)
from app.utils.time import utcnow


def _excerpt(text: str, limit: int = 90) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _normalized_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_candidate_ready_for_dispatch(
    candidate: ContentCandidate,
    now: datetime,
    *,
    include_unscheduled: bool,
) -> bool:
    status = ContentCandidateStatus(candidate.status)
    if status != ContentCandidateStatus.APPROVED:
        return False
    if candidate.published_at is not None:
        return False
    if candidate.content_type == str(ContentType.PREVIEW):
        return True
    if candidate.scheduled_at is None:
        return include_unscheduled
    return _normalized_datetime(candidate.scheduled_at) <= _normalized_datetime(now)


def validate_candidate_can_publish(candidate: ContentCandidate) -> None:
    status = ContentCandidateStatus(candidate.status)
    if status == ContentCandidateStatus.PUBLISHED or candidate.published_at is not None:
        raise InvalidStateTransitionError(f"El candidato {candidate.id} ya esta publicado")
    if status != ContentCandidateStatus.APPROVED:
        raise InvalidStateTransitionError(
            f"Solo se pueden publicar candidatos aprobados. Estado actual: {status}"
        )


class PublicationDispatcherService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _candidate(self, candidate_id: int) -> ContentCandidate:
        candidate = self.session.get(ContentCandidate, candidate_id)
        if candidate is None:
            raise ConfigurationError(f"Content candidate desconocido: {candidate_id}")
        return candidate

    def _ready_condition(self, now: datetime, include_unscheduled: bool):
        preview_ready = ContentCandidate.content_type == str(ContentType.PREVIEW)
        if include_unscheduled:
            return or_(
                preview_ready,
                ContentCandidate.scheduled_at.is_(None),
                ContentCandidate.scheduled_at <= now,
            )
        return or_(
            preview_ready,
            and_(ContentCandidate.scheduled_at.is_not(None), ContentCandidate.scheduled_at <= now),
        )

    def _row_to_view(self, row: ContentCandidate) -> PublicationCandidateView:
        return PublicationCandidateView(
            id=row.id,
            competition_slug=row.competition_slug,
            content_type=ContentType(row.content_type),
            priority=row.priority,
            status=ContentCandidateStatus(row.status),
            scheduled_at=row.scheduled_at,
            published_at=row.published_at,
            created_at=row.created_at,
            excerpt=_excerpt(row.text_draft),
        )

    def list_ready(
        self,
        *,
        now: datetime | None = None,
        include_unscheduled: bool = True,
        limit: int = 50,
    ) -> list[PublicationCandidateView]:
        ready_at = now or utcnow()
        ready_condition = self._ready_condition(ready_at, include_unscheduled)
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.APPROVED),
                ContentCandidate.published_at.is_(None),
                ready_condition,
            )
            .order_by(
                case((ContentCandidate.scheduled_at.is_(None), 1), else_=0),
                ContentCandidate.scheduled_at.asc(),
                ContentCandidate.priority.desc(),
                ContentCandidate.created_at.asc(),
            )
            .limit(limit)
        )
        rows = self.session.execute(query).scalars().all()
        return [self._row_to_view(row) for row in rows]

    def dispatch(
        self,
        *,
        now: datetime | None = None,
        limit: int = 20,
        dry_run: bool = False,
        include_unscheduled: bool = False,
    ) -> PublicationDispatchResult:
        dispatch_at = now or utcnow()
        ready_condition = self._ready_condition(dispatch_at, include_unscheduled)
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.APPROVED),
                ContentCandidate.published_at.is_(None),
                ready_condition,
            )
            .order_by(
                case((ContentCandidate.scheduled_at.is_(None), 1), else_=0),
                ContentCandidate.scheduled_at.asc(),
                ContentCandidate.priority.desc(),
                ContentCandidate.created_at.asc(),
            )
            .limit(limit)
        )
        rows = self.session.execute(query).scalars().all()
        if not dry_run:
            for row in rows:
                validate_candidate_can_publish(row)
                row.status = str(ContentCandidateStatus.PUBLISHED)
                row.published_at = dispatch_at
                self.session.add(row)
            if rows:
                self.session.flush()
        return PublicationDispatchResult(
            dry_run=dry_run,
            dispatched_count=len(rows),
            rows=[self._row_to_view(row) for row in rows],
        )

    def dispatch_candidates(
        self,
        candidate_ids: list[int],
        *,
        published_at: datetime | None = None,
        dry_run: bool = False,
        only_ready: bool = False,
        include_unscheduled: bool = True,
    ) -> PublicationDispatchResult:
        if not candidate_ids:
            return PublicationDispatchResult(dry_run=dry_run, dispatched_count=0, rows=[])
        dispatch_at = published_at or utcnow()
        rows = self.session.execute(
            select(ContentCandidate)
            .where(ContentCandidate.id.in_(candidate_ids))
            .order_by(
                ContentCandidate.priority.desc(),
                ContentCandidate.created_at.asc(),
            )
        ).scalars().all()
        if only_ready:
            rows = [
                row
                for row in rows
                if is_candidate_ready_for_dispatch(
                    row,
                    dispatch_at,
                    include_unscheduled=include_unscheduled,
                )
            ]
        for row in rows:
            validate_candidate_can_publish(row)
        if not dry_run:
            for row in rows:
                row.status = str(ContentCandidateStatus.PUBLISHED)
                row.published_at = dispatch_at
                self.session.add(row)
            self.session.flush()
        return PublicationDispatchResult(
            dry_run=dry_run,
            dispatched_count=len(rows),
            rows=[self._row_to_view(row) for row in rows],
        )

    def publish_candidate(
        self,
        candidate_id: int,
        *,
        published_at: datetime | None = None,
        external_publication_ref: str | None = None,
    ) -> PublicationCandidateView:
        timestamp = published_at or utcnow()
        candidate = self._candidate(candidate_id)
        validate_candidate_can_publish(candidate)
        candidate.status = str(ContentCandidateStatus.PUBLISHED)
        candidate.published_at = timestamp
        if external_publication_ref is not None:
            candidate.external_publication_ref = external_publication_ref
        self.session.add(candidate)
        self.session.flush()
        return self._row_to_view(candidate)

    def summary(self, *, now: datetime | None = None) -> PublicationDispatchSummary:
        reference = now or utcnow()
        total_ready = self.session.scalar(
            select(func.count())
            .select_from(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.APPROVED),
                ContentCandidate.published_at.is_(None),
                or_(ContentCandidate.scheduled_at.is_(None), ContentCandidate.scheduled_at <= reference),
            )
        ) or 0
        total_approved_future = self.session.scalar(
            select(func.count())
            .select_from(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.APPROVED),
                ContentCandidate.published_at.is_(None),
                ContentCandidate.scheduled_at.is_not(None),
                ContentCandidate.scheduled_at > reference,
            )
        ) or 0
        status_rows = self.session.execute(
            select(ContentCandidate.status, func.count())
            .group_by(ContentCandidate.status)
            .order_by(ContentCandidate.status)
        ).all()
        counts = {status: count for status, count in status_rows}
        return PublicationDispatchSummary(
            total_ready=total_ready,
            total_approved_future=total_approved_future,
            total_published=counts.get(str(ContentCandidateStatus.PUBLISHED), 0),
            total_rejected=counts.get(str(ContentCandidateStatus.REJECTED), 0),
            total_drafts=counts.get(str(ContentCandidateStatus.DRAFT), 0),
        )
