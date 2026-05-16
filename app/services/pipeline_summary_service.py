from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus
from app.db.models import ContentCandidate
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

# Thresholds for alert generation
_DEFAULT_REJECTION_ALERT_THRESHOLD = 5
_STUCK_PUBLISHED_HOURS = 2


@dataclass
class BlockedCandidateSummary:
    """Aggregate info for candidates blocked in draft or rejected status."""

    draft_count: int
    rejected_count: int
    # rejection_reason -> count (top reasons)
    rejection_reason_counts: dict[str, int]
    # quality check error code -> count (aggregated from quality_check_errors lists)
    quality_error_counts: dict[str, int]
    # content_type -> count of blocked candidates
    by_content_type: dict[str, int]
    # competition_slug -> count of blocked candidates
    by_competition: dict[str, int]


@dataclass
class PublicationCandidateEntry:
    id: int
    content_type: str
    competition_slug: str
    published_at: datetime | None
    external_publication_ref: str | None
    external_publication_error: str | None


@dataclass
class PublicationSummary:
    """Summary of published candidates and their X-publication state."""

    window_hours: int
    published_to_x: int            # browser: ref present
    skipped_stale: int             # pre_browser:skipped ref
    publication_errors: int        # external_publication_error not null
    pending_dispatch: int          # published, no ref, no error
    error_entries: list[PublicationCandidateEntry]
    pending_entries: list[PublicationCandidateEntry]


@dataclass
class PipelineAlert:
    level: str   # "ERROR" | "WARNING"
    code: str
    message: str


@dataclass
class PipelineSummaryReport:
    reference_date: date
    window_days: int
    generated_at: datetime
    blocked: BlockedCandidateSummary
    publication: PublicationSummary
    alerts: list[PipelineAlert]

    @property
    def has_alerts(self) -> bool:
        return bool(self.alerts)


class PipelineSummaryService:
    """Produces operational summaries of the content pipeline state.

    Reads only — does not modify any candidates.
    """

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        rejection_alert_threshold: int = _DEFAULT_REJECTION_ALERT_THRESHOLD,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.rejection_alert_threshold = rejection_alert_threshold

    def summary(
        self,
        reference_date: date | None = None,
        window_days: int = 2,
    ) -> PipelineSummaryReport:
        ref_date = reference_date or date.today()
        now = utcnow()
        window_start = now - timedelta(days=window_days)

        blocked = self._build_blocked_summary(window_start)
        publication = self._build_publication_summary(window_start)
        alerts = self._build_alerts(blocked, publication, window_start)

        return PipelineSummaryReport(
            reference_date=ref_date,
            window_days=window_days,
            generated_at=now,
            blocked=blocked,
            publication=publication,
            alerts=alerts,
        )

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_blocked_summary(self, window_start: datetime) -> BlockedCandidateSummary:
        rows = self.session.execute(
            select(ContentCandidate).where(
                ContentCandidate.status.in_([
                    str(ContentCandidateStatus.DRAFT),
                    str(ContentCandidateStatus.REJECTED),
                ]),
                ContentCandidate.created_at >= window_start,
            )
        ).scalars().all()

        draft_count = 0
        rejected_count = 0
        rejection_reason_counter: Counter[str] = Counter()
        quality_error_counter: Counter[str] = Counter()
        content_type_counter: Counter[str] = Counter()
        competition_counter: Counter[str] = Counter()

        for row in rows:
            if row.status == str(ContentCandidateStatus.DRAFT):
                draft_count += 1
            else:
                rejected_count += 1
                reason = row.rejection_reason
                if reason:
                    rejection_reason_counter[reason.strip()] += 1
                else:
                    rejection_reason_counter["(sin motivo)"] += 1

            content_type_counter[row.content_type] += 1
            competition_counter[row.competition_slug] += 1

            # Aggregate quality_check_errors (list of error code strings)
            if row.quality_check_errors:
                errors = row.quality_check_errors
                if isinstance(errors, list):
                    for err in errors:
                        if isinstance(err, str):
                            quality_error_counter[err] += 1

        return BlockedCandidateSummary(
            draft_count=draft_count,
            rejected_count=rejected_count,
            rejection_reason_counts=dict(rejection_reason_counter.most_common()),
            quality_error_counts=dict(quality_error_counter.most_common()),
            by_content_type=dict(content_type_counter.most_common()),
            by_competition=dict(competition_counter.most_common()),
        )

    def _build_publication_summary(self, window_start: datetime) -> PublicationSummary:
        window_hours = int((utcnow() - window_start).total_seconds() // 3600)

        rows = self.session.execute(
            select(ContentCandidate).where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.published_at >= window_start,
            )
        ).scalars().all()

        published_to_x = 0
        skipped_stale = 0
        publication_errors = 0
        pending_dispatch = 0
        error_entries: list[PublicationCandidateEntry] = []
        pending_entries: list[PublicationCandidateEntry] = []

        for row in rows:
            ref = row.external_publication_ref
            err = row.external_publication_error

            entry = PublicationCandidateEntry(
                id=row.id,
                content_type=row.content_type,
                competition_slug=row.competition_slug,
                published_at=row.published_at,
                external_publication_ref=ref,
                external_publication_error=err,
            )

            if ref and ref.startswith("browser:"):
                published_to_x += 1
            elif ref == "pre_browser:skipped":
                skipped_stale += 1
            elif err:
                publication_errors += 1
                error_entries.append(entry)
            else:
                # published but no ref and no error — pending dispatch
                pending_dispatch += 1
                pending_entries.append(entry)

        return PublicationSummary(
            window_hours=window_hours,
            published_to_x=published_to_x,
            skipped_stale=skipped_stale,
            publication_errors=publication_errors,
            pending_dispatch=pending_dispatch,
            error_entries=error_entries,
            pending_entries=pending_entries,
        )

    def _build_alerts(
        self,
        blocked: BlockedCandidateSummary,
        publication: PublicationSummary,
        window_start: datetime,
    ) -> list[PipelineAlert]:
        alerts: list[PipelineAlert] = []

        # Alert: publication errors in the window
        if publication.publication_errors > 0:
            ids = ", ".join(str(e.id) for e in publication.error_entries[:5])
            suffix = f" ... (+{publication.publication_errors - 5} mas)" if publication.publication_errors > 5 else ""
            alerts.append(PipelineAlert(
                level="ERROR",
                code="publication_errors",
                message=(
                    f"{publication.publication_errors} candidato(s) con error de publicacion en X "
                    f"en las ultimas {publication.window_hours}h. IDs: {ids}{suffix}"
                ),
            ))

        # Alert: too many rejections in the last 24h
        last_24h = utcnow() - timedelta(hours=24)
        recent_rejected = self.session.execute(
            select(ContentCandidate).where(
                ContentCandidate.status == str(ContentCandidateStatus.REJECTED),
                ContentCandidate.created_at >= last_24h,
            )
        ).scalars().all()
        if len(recent_rejected) >= self.rejection_alert_threshold:
            alerts.append(PipelineAlert(
                level="WARNING",
                code="high_rejection_rate",
                message=(
                    f"{len(recent_rejected)} candidato(s) rechazados en las ultimas 24h "
                    f"(umbral: {self.rejection_alert_threshold})."
                ),
            ))

        # Alert: stuck published candidates (published >2h ago, no ref, no error)
        stuck_cutoff = utcnow() - timedelta(hours=_STUCK_PUBLISHED_HOURS)
        stuck = [
            e for e in publication.pending_entries
            if e.published_at is not None
            and _ensure_utc(e.published_at) < stuck_cutoff
        ]
        if stuck:
            ids = ", ".join(str(e.id) for e in stuck[:5])
            suffix = f" ... (+{len(stuck) - 5} mas)" if len(stuck) > 5 else ""
            alerts.append(PipelineAlert(
                level="WARNING",
                code="stuck_published",
                message=(
                    f"{len(stuck)} candidato(s) en estado 'published' hace mas de "
                    f"{_STUCK_PUBLISHED_HOURS}h sin ref ni error de publicacion. IDs: {ids}{suffix}"
                ),
            ))

        return alerts


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
