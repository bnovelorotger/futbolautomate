from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.channels.x.client import XApiClient, XApiError
from app.channels.x.publisher import XPublisher, XPublisherValidationError
from app.core.config import get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.schemas.x_publication import (
    XBatchPublicationResult,
    XPublicationCandidateView,
    XPublicationResult,
)
from app.services.editorial_text_selector import EditorialTextSelectorService
from app.services.x_publication_scheduler import XPublicationScheduler
from app.services.x_auth_service import XAuthService
from app.channels.x.auth import XAuthError
from app.utils.time import utcnow


def _excerpt(text: str, limit: int = 90) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def is_candidate_eligible_for_x(candidate: ContentCandidate) -> bool:
    return (
        candidate.status == str(ContentCandidateStatus.PUBLISHED)
        and candidate.external_publication_ref is None
        and bool(candidate.text_draft.strip())
    )


class XPublicationService:
    def __init__(
        self,
        session: Session,
        *,
        publisher: XPublisher | None = None,
        auth_service: XAuthService | None = None,
        text_selector: EditorialTextSelectorService | None = None,
        scheduler: XPublicationScheduler | None = None,
    ) -> None:
        self.session = session
        settings = get_settings()
        self.publisher = publisher or XPublisher(XApiClient(settings))
        self.auth_service = auth_service or XAuthService(session, settings=settings)
        self.text_selector = text_selector or EditorialTextSelectorService(session, settings=settings)
        self.scheduler = scheduler or XPublicationScheduler(settings=settings)

    def _candidate(self, candidate_id: int) -> ContentCandidate:
        candidate = self.session.get(ContentCandidate, candidate_id)
        if candidate is None:
            raise ConfigurationError(f"Content candidate desconocido: {candidate_id}")
        return candidate

    def _selected_text(self, candidate: ContentCandidate) -> tuple[str, str]:
        selection = self.text_selector.select_text(candidate, prefer_rewrite=True)
        return selection.text, selection.source

    def _validate_candidate(self, candidate: ContentCandidate) -> tuple[str, str]:
        if candidate.status != str(ContentCandidateStatus.PUBLISHED):
            raise InvalidStateTransitionError(
                f"Solo se pueden publicar en X piezas con estado interno published. Estado actual: {candidate.status}"
            )
        if candidate.external_publication_ref:
            raise InvalidStateTransitionError(
                f"El candidato {candidate.id} ya tiene external_publication_ref={candidate.external_publication_ref}"
            )
        try:
            return self._selected_text(candidate)
        except InvalidStateTransitionError as exc:
            raise InvalidStateTransitionError(
                f"El candidato {candidate.id} no tiene texto utilizable para X: {exc}"
            ) from exc

    def _row_to_view(self, row: ContentCandidate) -> XPublicationCandidateView:
        selected_text_source: str | None = None
        excerpt = _excerpt(row.text_draft)
        try:
            selected_text, selected_text_source = self._selected_text(row)
            excerpt = _excerpt(selected_text)
        except InvalidStateTransitionError:
            pass
        return XPublicationCandidateView(
            id=row.id,
            competition_slug=row.competition_slug,
            content_type=ContentType(row.content_type),
            priority=row.priority,
            status=ContentCandidateStatus(row.status),
            selected_text_source=selected_text_source,
            scheduled_at=row.scheduled_at,
            external_publication_ref=row.external_publication_ref,
            external_publication_timestamp=row.external_publication_timestamp,
            external_publication_attempted_at=row.external_publication_attempted_at,
            external_publication_error=row.external_publication_error,
            excerpt=excerpt,
        )

    def list_pending(self, *, limit: int = 50) -> list[XPublicationCandidateView]:
        rows = self._pending_candidates(limit=limit)
        return [self._row_to_view(row) for row in rows]

    def _pending_candidates(self, *, limit: int | None = None) -> list[ContentCandidate]:
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
                func.length(func.trim(ContentCandidate.text_draft)) > 0,
            )
            .order_by(
                case((ContentCandidate.published_at.is_(None), 1), else_=0),
                ContentCandidate.published_at.asc(),
                ContentCandidate.priority.desc(),
                ContentCandidate.created_at.asc(),
            )
        )
        if limit is not None:
            query = query.limit(limit)
        return self.session.execute(query).scalars().all()

    def publish_candidate(self, candidate_id: int, *, dry_run: bool = False) -> XPublicationResult:
        candidate = self._candidate(candidate_id)
        selected_text, _ = self._validate_candidate(candidate)
        if dry_run:
            self.publisher.publish_text(selected_text, dry_run=True)
            return XPublicationResult(dry_run=True, candidate=self._row_to_view(candidate))

        attempted_at = utcnow()
        candidate.publication_attempts = (candidate.publication_attempts or 0) + 1
        try:
            access_token = self.auth_service.get_valid_user_access_token()
            response = self.publisher.publish_text(
                selected_text,
                access_token=access_token,
                dry_run=False,
            )
        except (XAuthError, XApiError, XPublisherValidationError) as exc:
            candidate.external_publication_attempted_at = attempted_at
            candidate.external_publication_error = str(exc)
            self.session.add(candidate)
            self.session.flush()
            raise

        candidate.external_publication_ref = response.post_id
        candidate.external_channel = "x"
        candidate.external_exported_at = response.published_at
        candidate.external_publication_timestamp = response.published_at
        candidate.external_publication_attempted_at = attempted_at
        candidate.external_publication_error = None
        self.session.add(candidate)
        self.session.flush()
        return XPublicationResult(dry_run=False, candidate=self._row_to_view(candidate))

    def publish_candidates(
        self,
        candidate_ids: list[int],
        *,
        dry_run: bool = False,
        respect_schedule: bool = True,
    ) -> XBatchPublicationResult:
        result_rows: list[XPublicationCandidateView] = []
        candidates = [self.session.get(ContentCandidate, candidate_id) for candidate_id in candidate_ids]
        selected_candidates = [candidate for candidate in candidates if candidate is not None]
        if respect_schedule:
            selected_candidates = self.scheduler.filter_candidates(selected_candidates)
        for candidate in selected_candidates:
            try:
                result = self.publish_candidate(candidate.id, dry_run=dry_run)
            except (XAuthError, XApiError, XPublisherValidationError, InvalidStateTransitionError, ConfigurationError):
                result_rows.append(self._row_to_view(candidate))
                continue
            result_rows.append(result.candidate)
        published_count = sum(1 for row in result_rows if row.external_publication_ref)
        if dry_run:
            published_count = len(result_rows)
        return XBatchPublicationResult(
            dry_run=dry_run,
            published_count=published_count,
            rows=result_rows,
        )

    def publish_pending(
        self,
        *,
        limit: int = 20,
        dry_run: bool = False,
    ) -> XBatchPublicationResult:
        rows = self.scheduler.filter_candidates(self._pending_candidates())
        return self.publish_candidates([row.id for row in rows[:limit]], dry_run=dry_run, respect_schedule=False)
