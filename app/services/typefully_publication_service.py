from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.channels.typefully.client import TypefullyApiClient, TypefullyApiError
from app.channels.typefully.publisher import TypefullyPublisher, TypefullyPublisherValidationError
from app.channels.typefully.schemas import TypefullyPublishResponse
from app.core.config import get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.services.editorial_text_selector import EditorialTextSelectorService
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

_DEFAULT_SCHEDULE_PATH = Path(__file__).resolve().parents[1] / "config" / "typefully_schedule.json"


def _load_schedule_config(path: Path | None = None) -> dict:
    schedule_path = path or _DEFAULT_SCHEDULE_PATH
    with schedule_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _excerpt(text: str, limit: int = 90) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


@dataclass
class TypefullyPublicationCandidateView:
    id: int
    competition_slug: str
    content_type: str
    priority: int
    status: str
    excerpt: str
    external_publication_ref: str | None = None
    external_publication_timestamp: datetime | None = None
    external_publication_attempted_at: datetime | None = None
    external_publication_error: str | None = None
    scheduled_typefully_date: datetime | None = None


@dataclass
class TypefullyPublishResult:
    dry_run: bool
    candidate: TypefullyPublicationCandidateView


@dataclass
class TypefullyBatchResult:
    dry_run: bool
    published_count: int
    rows: list[TypefullyPublicationCandidateView] = field(default_factory=list)


def is_candidate_eligible_for_typefully(candidate: ContentCandidate) -> bool:
    return (
        candidate.status == str(ContentCandidateStatus.PUBLISHED)
        and candidate.external_publication_ref is None
        and bool(candidate.text_draft.strip())
    )


class TypefullyPublicationService:
    def __init__(
        self,
        session: Session,
        *,
        publisher: TypefullyPublisher | None = None,
        text_selector: EditorialTextSelectorService | None = None,
        schedule_config: dict | None = None,
    ) -> None:
        self.session = session
        if publisher is None:
            settings = get_settings()
            client = TypefullyApiClient(api_key=settings.typefully_api_key or "")
            publisher = TypefullyPublisher(client)
        self.publisher = publisher
        self.text_selector = text_selector or EditorialTextSelectorService(session)
        self.schedule_config = schedule_config or _load_schedule_config()

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
                f"Solo se pueden publicar en Typefully piezas con estado interno published. Estado actual: {candidate.status}"
            )
        if candidate.external_publication_ref:
            raise InvalidStateTransitionError(
                f"El candidato {candidate.id} ya tiene external_publication_ref={candidate.external_publication_ref}"
            )
        try:
            return self._selected_text(candidate)
        except InvalidStateTransitionError as exc:
            raise InvalidStateTransitionError(
                f"El candidato {candidate.id} no tiene texto utilizable para Typefully: {exc}"
            ) from exc

    def _row_to_view(
        self,
        row: ContentCandidate,
        *,
        scheduled_typefully_date: datetime | None = None,
    ) -> TypefullyPublicationCandidateView:
        excerpt = _excerpt(row.text_draft)
        try:
            selected_text, _ = self._selected_text(row)
            excerpt = _excerpt(selected_text)
        except InvalidStateTransitionError:
            pass
        return TypefullyPublicationCandidateView(
            id=row.id,
            competition_slug=row.competition_slug,
            content_type=row.content_type,
            priority=row.priority,
            status=row.status,
            excerpt=excerpt,
            external_publication_ref=row.external_publication_ref,
            external_publication_timestamp=row.external_publication_timestamp,
            external_publication_attempted_at=row.external_publication_attempted_at,
            external_publication_error=row.external_publication_error,
            scheduled_typefully_date=scheduled_typefully_date,
        )

    def _schedule_date_for(self, content_type: str, post_index: int = 0) -> datetime:
        """Returns UTC datetime for when this post should go live on Typefully.

        Uses content_type_delays_minutes from schedule_config plus stagger per post_index.
        Base time is now (UTC) so Typefully schedules it relative to the current moment.
        """
        stagger = self.schedule_config.get("stagger_between_posts_minutes", 5)
        content_delays: dict = self.schedule_config.get("content_type_delays_minutes", {})
        type_delay = content_delays.get(content_type, 0)
        total_minutes = type_delay + stagger * post_index
        return utcnow().replace(second=0, microsecond=0) + timedelta(minutes=total_minutes)

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

    def publish_candidate(
        self,
        candidate_id: int,
        *,
        dry_run: bool = False,
        post_index: int = 0,
    ) -> TypefullyPublishResult:
        candidate = self._candidate(candidate_id)
        selected_text, _ = self._validate_candidate(candidate)
        schedule_date = self._schedule_date_for(candidate.content_type, post_index)

        if dry_run:
            self.publisher.publish_text(selected_text, dry_run=True)
            return TypefullyPublishResult(
                dry_run=True,
                candidate=self._row_to_view(candidate, scheduled_typefully_date=schedule_date),
            )

        attempted_at = utcnow()
        candidate.publication_attempts = (candidate.publication_attempts or 0) + 1
        try:
            response: TypefullyPublishResponse = self.publisher.publish_text(
                selected_text,
                schedule_date=schedule_date,
                dry_run=False,
            )
        except (TypefullyApiError, TypefullyPublisherValidationError) as exc:
            candidate.external_publication_attempted_at = attempted_at
            candidate.external_publication_error = str(exc)
            self.session.add(candidate)
            self.session.flush()
            raise

        candidate.external_publication_ref = response.draft_id
        candidate.external_channel = "typefully"
        candidate.external_exported_at = attempted_at
        candidate.external_publication_timestamp = response.scheduled_date or attempted_at
        candidate.external_publication_attempted_at = attempted_at
        candidate.external_publication_error = None
        self.session.add(candidate)
        self.session.flush()
        return TypefullyPublishResult(
            dry_run=False,
            candidate=self._row_to_view(candidate, scheduled_typefully_date=schedule_date),
        )

    def publish_pending(
        self,
        *,
        limit: int = 20,
        dry_run: bool = False,
    ) -> TypefullyBatchResult:
        candidates = self._pending_candidates(limit=limit)
        result_rows: list[TypefullyPublicationCandidateView] = []
        for index, candidate in enumerate(candidates):
            try:
                result = self.publish_candidate(candidate.id, dry_run=dry_run, post_index=index)
            except (TypefullyApiError, TypefullyPublisherValidationError, InvalidStateTransitionError, ConfigurationError):
                result_rows.append(self._row_to_view(candidate))
                continue
            result_rows.append(result.candidate)
        published_count = sum(1 for row in result_rows if row.external_publication_ref)
        if dry_run:
            published_count = len(result_rows)
        return TypefullyBatchResult(
            dry_run=dry_run,
            published_count=published_count,
            rows=result_rows,
        )
