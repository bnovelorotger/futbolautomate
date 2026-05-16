from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from datetime import timedelta

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.channels.x_browser.publisher import (
    XBrowserPublishError,
    XBrowserPublisher,
    XBrowserSessionError,
)
from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.services.editorial_text_selector import EditorialTextSelectorService
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def _excerpt(text: str, limit: int = 90) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


@dataclass
class XBrowserPublicationResult:
    candidate_id: int
    competition_slug: str
    content_type: str
    dry_run: bool
    success: bool
    external_publication_ref: str | None = None
    error: str | None = None
    excerpt: str = ""


@dataclass
class XBrowserBatchResult:
    dry_run: bool
    published_count: int
    error_count: int
    skipped_count: int
    rows: list[XBrowserPublicationResult] = field(default_factory=list)


class XBrowserPublicationService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        publisher: XBrowserPublisher | None = None,
        text_selector: EditorialTextSelectorService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.text_selector = text_selector or EditorialTextSelectorService(session, settings=self.settings)
        state_file = Path(self.settings.x_browser_state_file)
        self.publisher = publisher or XBrowserPublisher(
            state_file,
            headless=self.settings.x_browser_headless,
            typing_delay_ms=self.settings.x_browser_typing_delay_ms,
        )

    def _selected_text(self, candidate: ContentCandidate) -> tuple[str, str]:
        selection = self.text_selector.select_text(candidate, prefer_rewrite=True)
        return selection.text, selection.source

    def mark_pre_browser_published(self, *, cutoff_hours: int = 48) -> None:
        """Mark old published candidates as handled so they are never queued for browser publish.

        Candidates published more than cutoff_hours ago predate the browser publisher
        and should not be re-published to X as they would flood the timeline with stale content.
        """
        from app.utils.time import utcnow
        cutoff = utcnow() - timedelta(hours=cutoff_hours)
        self.session.execute(
            update(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
                ContentCandidate.published_at < cutoff,
            )
            .values(external_publication_ref="pre_browser:skipped")
        )

    def _pending_candidates(self, *, limit: int | None = None) -> list[ContentCandidate]:
        from app.utils.time import utcnow
        cutoff = utcnow() - timedelta(hours=48)
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
                func.length(func.trim(ContentCandidate.text_draft)) > 0,
                ContentCandidate.published_at >= cutoff,
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
        return list(self.session.execute(query).scalars().all())

    def publish_pending(
        self,
        *,
        limit: int = 20,
        dry_run: bool = False,
        stagger_seconds: int | None = None,
    ) -> XBrowserBatchResult:
        if stagger_seconds is None:
            stagger_seconds = self.settings.x_browser_stagger_seconds

        candidates = self._pending_candidates(limit=limit)
        rows: list[XBrowserPublicationResult] = []
        published_count = 0
        error_count = 0

        for idx, candidate in enumerate(candidates):
            try:
                selected_text, _ = self._selected_text(candidate)
            except InvalidStateTransitionError as exc:
                logger.warning(
                    "Candidato %s sin texto utilizable para x_browser: %s",
                    candidate.id,
                    exc,
                )
                rows.append(
                    XBrowserPublicationResult(
                        candidate_id=candidate.id,
                        competition_slug=candidate.competition_slug or "",
                        content_type=candidate.content_type or "",
                        dry_run=dry_run,
                        success=False,
                        error=str(exc),
                        excerpt=_excerpt(candidate.text_draft or ""),
                    )
                )
                error_count += 1
                continue

            excerpt = _excerpt(selected_text)

            # Stagger between posts (skip before the first one)
            if idx > 0 and not dry_run and stagger_seconds > 0:
                logger.info("Esperando %ss antes del siguiente tweet…", stagger_seconds)
                time.sleep(stagger_seconds)

            attempted_at = utcnow()
            candidate.publication_attempts = (candidate.publication_attempts or 0) + 1

            try:
                response = self.publisher.publish_text(selected_text, dry_run=dry_run)
            except XBrowserSessionError as exc:
                # Session is broken — abort the entire batch
                logger.error("Sesion de browser X invalida, abortando batch: %s", exc)
                candidate.external_publication_attempted_at = attempted_at
                candidate.external_publication_error = str(exc)
                self.session.add(candidate)
                self.session.flush()
                rows.append(
                    XBrowserPublicationResult(
                        candidate_id=candidate.id,
                        competition_slug=candidate.competition_slug or "",
                        content_type=candidate.content_type or "",
                        dry_run=dry_run,
                        success=False,
                        error=str(exc),
                        excerpt=excerpt,
                    )
                )
                error_count += 1
                break
            except XBrowserPublishError as exc:
                logger.error(
                    "Error publicando candidato %s via browser: %s",
                    candidate.id,
                    exc,
                )
                candidate.external_publication_attempted_at = attempted_at
                candidate.external_publication_error = str(exc)
                self.session.add(candidate)
                self.session.flush()
                rows.append(
                    XBrowserPublicationResult(
                        candidate_id=candidate.id,
                        competition_slug=candidate.competition_slug or "",
                        content_type=candidate.content_type or "",
                        dry_run=dry_run,
                        success=False,
                        error=str(exc),
                        excerpt=excerpt,
                    )
                )
                error_count += 1
                continue

            if not dry_run:
                timestamp = response.published_at or utcnow()
                ref = f"browser:{timestamp.isoformat()}"
                candidate.external_publication_ref = ref
                candidate.external_channel = "x_browser"
                candidate.external_exported_at = timestamp
                candidate.external_publication_timestamp = timestamp
                candidate.external_publication_attempted_at = attempted_at
                candidate.external_publication_error = None
                self.session.add(candidate)
                self.session.flush()
                rows.append(
                    XBrowserPublicationResult(
                        candidate_id=candidate.id,
                        competition_slug=candidate.competition_slug or "",
                        content_type=candidate.content_type or "",
                        dry_run=False,
                        success=True,
                        external_publication_ref=ref,
                        excerpt=excerpt,
                    )
                )
            else:
                rows.append(
                    XBrowserPublicationResult(
                        candidate_id=candidate.id,
                        competition_slug=candidate.competition_slug or "",
                        content_type=candidate.content_type or "",
                        dry_run=True,
                        success=True,
                        excerpt=excerpt,
                    )
                )

            published_count += 1

        return XBrowserBatchResult(
            dry_run=dry_run,
            published_count=published_count,
            error_count=error_count,
            skipped_count=len(candidates) - published_count - error_count,
            rows=rows,
        )
