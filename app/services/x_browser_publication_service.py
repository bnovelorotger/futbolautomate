from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.channels.x_browser.publisher import (
    XBrowserPublishError,
    XBrowserPublisher,
    XBrowserSessionError,
)
from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.schemas.x_publication import (
    XBatchPublicationResult,
    XPublicationCandidateView,
    XPublicationResult,
)
from app.services.editorial_candidate_window import EditorialCandidateWindowService
from app.services.editorial_text_selector import EditorialTextSelectorService
from app.services.x_publication_scheduler import XPublicationScheduler
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
    selected_text_source: str | None = None
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
        scheduler: XPublicationScheduler | None = None,
        window_service: EditorialCandidateWindowService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.text_selector = text_selector or EditorialTextSelectorService(session, settings=self.settings)
        self.scheduler = scheduler or XPublicationScheduler(settings=self.settings)
        self.window_service = window_service or EditorialCandidateWindowService(session, settings=self.settings)
        state_file = Path(self.settings.x_browser_state_file)
        self.publisher = publisher or XBrowserPublisher(
            state_file,
            headless=self.settings.x_browser_headless,
            typing_delay_ms=self.settings.x_browser_typing_delay_ms,
        )

    def _candidate(self, candidate_id: int) -> ContentCandidate:
        candidate = self.session.get(ContentCandidate, candidate_id)
        if candidate is None:
            raise ConfigurationError(f"Content candidate desconocido: {candidate_id}")
        return candidate

    def _find_image_for_candidate(self, candidate: ContentCandidate) -> Path | None:
        try:
            competition_slug = candidate.competition_slug or ""
            exports_root = self.settings.app_root / "exports"
            pattern = f"images/{competition_slug}/**/standings_roundup_{candidate.id}.png"
            matches = sorted(
                exports_root.glob(pattern),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            return matches[0] if matches else None
        except Exception:
            return None

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

    def _row_to_view(
        self,
        candidate: ContentCandidate,
        *,
        selected_text_source: str | None = None,
        excerpt: str | None = None,
    ) -> XPublicationCandidateView:
        resolved_source = selected_text_source
        resolved_excerpt = excerpt or _excerpt(candidate.text_draft or "")
        if resolved_source is None:
            try:
                selected_text, resolved_source = self._selected_text(candidate)
                resolved_excerpt = _excerpt(selected_text)
            except InvalidStateTransitionError:
                pass
        return XPublicationCandidateView(
            id=candidate.id,
            competition_slug=candidate.competition_slug,
            content_type=ContentType(candidate.content_type),
            priority=candidate.priority,
            status=ContentCandidateStatus(candidate.status),
            selected_text_source=resolved_source,
            scheduled_at=candidate.scheduled_at,
            published_at=candidate.published_at,
            external_publication_ref=candidate.external_publication_ref,
            external_publication_timestamp=candidate.external_publication_timestamp,
            external_publication_attempted_at=candidate.external_publication_attempted_at,
            external_publication_error=candidate.external_publication_error,
            excerpt=resolved_excerpt,
        )

    def _record_failure(
        self,
        candidate: ContentCandidate,
        *,
        attempted_at,
        error: str,
    ) -> None:
        candidate.publication_attempts = (candidate.publication_attempts or 0) + 1
        candidate.external_publication_attempted_at = attempted_at
        candidate.external_publication_error = error
        self.session.add(candidate)
        self.session.flush()

    def _apply_success(
        self,
        candidate: ContentCandidate,
        *,
        attempted_at,
        published_at,
    ) -> str:
        ref = f"x-browser:{published_at.isoformat()}"
        candidate.publication_attempts = (candidate.publication_attempts or 0) + 1
        candidate.external_publication_ref = ref
        candidate.external_channel = "x"
        candidate.external_exported_at = published_at
        candidate.external_publication_timestamp = published_at
        candidate.external_publication_attempted_at = attempted_at
        candidate.external_publication_error = None
        self.session.add(candidate)
        self.session.flush()
        return ref

    def mark_pre_browser_published(self, *, cutoff_hours: int = 48) -> None:
        """Mark old published candidates as handled so they are never queued for browser publish."""

        cutoff = self.scheduler.current_local_time() - timedelta(hours=cutoff_hours)
        self.session.execute(
            update(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
                ContentCandidate.published_at < cutoff,
            )
            .values(external_publication_ref="pre_browser:skipped")
            .execution_options(synchronize_session=False)
        )

    def _pending_candidates(self, *, limit: int | None = None) -> list[ContentCandidate]:
        cutoff = self.scheduler.current_local_time() - timedelta(hours=48)
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

    def _fresh_candidates(self, candidates: list[ContentCandidate]) -> list[ContentCandidate]:
        reference_date = self.scheduler.current_local_time().date()
        return [
            candidate
            for candidate in candidates
            if self.window_service.matches_release_window(candidate, reference_date=reference_date)
        ]

    def list_pending(self, *, limit: int = 50) -> list[XPublicationCandidateView]:
        rows = self.scheduler.filter_candidates(self._fresh_candidates(self._pending_candidates()))
        return [self._row_to_view(row) for row in rows[:limit]]

    def list_all_unpublished(self, *, limit: int = 100) -> list[XPublicationCandidateView]:
        """All published candidates without external_publication_ref, regardless of scheduler window."""
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
            )
            .order_by(
                case((ContentCandidate.published_at.is_(None), 1), else_=0),
                ContentCandidate.published_at.asc(),
            )
            .limit(limit)
        )
        rows = list(self.session.execute(query).scalars().all())
        return [self._row_to_view(row) for row in rows]

    def build_views_from_batch_result(
        self,
        batch_result: XBrowserBatchResult,
    ) -> list[XPublicationCandidateView]:
        views: list[XPublicationCandidateView] = []
        for row in batch_result.rows:
            candidate = self.session.get(ContentCandidate, row.candidate_id)
            if candidate is None:
                continue
            views.append(
                self._row_to_view(
                    candidate,
                    selected_text_source=row.selected_text_source,
                    excerpt=row.excerpt,
                )
            )
        return views

    def publish_candidate(self, candidate_id: int, *, dry_run: bool = False) -> XPublicationResult:
        candidate = self._candidate(candidate_id)
        selected_text, selected_text_source = self._validate_candidate(candidate)
        excerpt = _excerpt(selected_text)

        image_path: Path | None = None
        if candidate.content_type == str(ContentType.STANDINGS_ROUNDUP):
            image_path = self._find_image_for_candidate(candidate)

        if dry_run:
            self.publisher.publish_text(selected_text, image_path=image_path, dry_run=True)
            return XPublicationResult(
                dry_run=True,
                candidate=self._row_to_view(
                    candidate,
                    selected_text_source=selected_text_source,
                    excerpt=excerpt,
                ),
            )

        attempted_at = utcnow()
        try:
            response = self.publisher.publish_text(selected_text, image_path=image_path, dry_run=False)
        except (XBrowserSessionError, XBrowserPublishError) as exc:
            self._record_failure(candidate, attempted_at=attempted_at, error=str(exc))
            raise

        self._apply_success(
            candidate,
            attempted_at=attempted_at,
            published_at=response.published_at or utcnow(),
        )
        return XPublicationResult(
            dry_run=False,
            candidate=self._row_to_view(
                candidate,
                selected_text_source=selected_text_source,
                excerpt=excerpt,
            ),
        )

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
            selected_candidates = self.scheduler.filter_candidates(
                self._fresh_candidates(selected_candidates),
            )
        for candidate in selected_candidates:
            try:
                result = self.publish_candidate(candidate.id, dry_run=dry_run)
            except (XBrowserPublishError, InvalidStateTransitionError, ConfigurationError):
                result_rows.append(self._row_to_view(candidate))
                continue
            except XBrowserSessionError:
                result_rows.append(self._row_to_view(candidate))
                break
            result_rows.append(result.candidate)
        published_count = sum(1 for row in result_rows if row.external_publication_ref)
        if dry_run:
            published_count = len(result_rows)
        return XBatchPublicationResult(
            dry_run=dry_run,
            published_count=published_count,
            rows=result_rows,
        )

    def publish_standings_thread(
        self,
        *,
        dry_run: bool = False,
    ) -> XBrowserBatchResult:
        all_pending = self._pending_candidates()
        standings_candidates = [
            c for c in all_pending if c.content_type == str(ContentType.STANDINGS_ROUNDUP)
        ]
        standings_candidates = self.scheduler.filter_candidates(self._fresh_candidates(standings_candidates))

        if len(standings_candidates) < 2:
            return self.publish_pending(dry_run=dry_run)

        tweets: list[tuple[str, Path | None]] = []
        valid_candidates: list[ContentCandidate] = []
        for candidate in standings_candidates:
            try:
                selected_text, _ = self._validate_candidate(candidate)
            except InvalidStateTransitionError as exc:
                logger.warning("Candidato %s sin texto utilizable para thread: %s", candidate.id, exc)
                continue
            image_path = self._find_image_for_candidate(candidate)
            tweets.append((selected_text, image_path))
            valid_candidates.append(candidate)

        if len(valid_candidates) < 2:
            return self.publish_pending(dry_run=dry_run)

        rows: list[XBrowserPublicationResult] = []
        attempted_at = utcnow()

        try:
            response = self.publisher.publish_thread(tweets, dry_run=dry_run)
        except XBrowserSessionError as exc:
            logger.error("Sesion de browser X invalida al publicar thread de standings: %s", exc)
            if not dry_run:
                for candidate in valid_candidates:
                    self._record_failure(candidate, attempted_at=attempted_at, error=str(exc))
                    rows.append(
                        XBrowserPublicationResult(
                            candidate_id=candidate.id,
                            competition_slug=candidate.competition_slug or "",
                            content_type=candidate.content_type or "",
                            dry_run=dry_run,
                            success=False,
                            error=str(exc),
                        )
                    )
            return XBrowserBatchResult(
                dry_run=dry_run,
                published_count=0,
                error_count=len(valid_candidates),
                skipped_count=0,
                rows=rows,
            )
        except XBrowserPublishError as exc:
            logger.warning(
                "Thread publish failed (%s), falling back to individual publishing for standings candidates",
                exc,
            )
            return self.publish_pending(dry_run=dry_run)

        published_at = response.published_at or utcnow()
        for candidate in valid_candidates:
            if not dry_run:
                ref = self._apply_success(candidate, attempted_at=attempted_at, published_at=published_at)
                rows.append(
                    XBrowserPublicationResult(
                        candidate_id=candidate.id,
                        competition_slug=candidate.competition_slug or "",
                        content_type=candidate.content_type or "",
                        dry_run=False,
                        success=True,
                        external_publication_ref=ref,
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
                    )
                )

        return XBrowserBatchResult(
            dry_run=dry_run,
            published_count=len(valid_candidates),
            error_count=0,
            skipped_count=0,
            rows=rows,
        )

    def publish_pending(
        self,
        *,
        limit: int = 20,
        dry_run: bool = False,
        stagger_seconds: int | None = None,
    ) -> XBrowserBatchResult:
        if stagger_seconds is None:
            stagger_seconds = self.settings.x_browser_stagger_seconds

        if not dry_run:
            self.mark_pre_browser_published()

        candidates = self.scheduler.filter_candidates(self._fresh_candidates(self._pending_candidates()))
        candidates = candidates[:limit]
        rows: list[XBrowserPublicationResult] = []
        published_count = 0
        error_count = 0

        for idx, candidate in enumerate(candidates):
            try:
                selected_text, selected_text_source = self._validate_candidate(candidate)
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

            image_path: Path | None = None
            if candidate.content_type == str(ContentType.STANDINGS_ROUNDUP):
                image_path = self._find_image_for_candidate(candidate)

            if idx > 0 and not dry_run and stagger_seconds > 0:
                logger.info("Esperando %ss antes del siguiente tweet...", stagger_seconds)
                time.sleep(stagger_seconds)

            attempted_at = utcnow()
            try:
                response = self.publisher.publish_text(selected_text, image_path=image_path, dry_run=dry_run)
            except XBrowserSessionError as exc:
                logger.error("Sesion de browser X invalida, abortando batch: %s", exc)
                if not dry_run:
                    self._record_failure(candidate, attempted_at=attempted_at, error=str(exc))
                rows.append(
                    XBrowserPublicationResult(
                        candidate_id=candidate.id,
                        competition_slug=candidate.competition_slug or "",
                        content_type=candidate.content_type or "",
                        dry_run=dry_run,
                        success=False,
                        selected_text_source=selected_text_source,
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
                if not dry_run:
                    self._record_failure(candidate, attempted_at=attempted_at, error=str(exc))
                rows.append(
                    XBrowserPublicationResult(
                        candidate_id=candidate.id,
                        competition_slug=candidate.competition_slug or "",
                        content_type=candidate.content_type or "",
                        dry_run=dry_run,
                        success=False,
                        selected_text_source=selected_text_source,
                        error=str(exc),
                        excerpt=excerpt,
                    )
                )
                error_count += 1
                continue

            if not dry_run:
                ref = self._apply_success(
                    candidate,
                    attempted_at=attempted_at,
                    published_at=response.published_at or utcnow(),
                )
                rows.append(
                    XBrowserPublicationResult(
                        candidate_id=candidate.id,
                        competition_slug=candidate.competition_slug or "",
                        content_type=candidate.content_type or "",
                        dry_run=False,
                        success=True,
                        selected_text_source=selected_text_source,
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
                        selected_text_source=selected_text_source,
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
