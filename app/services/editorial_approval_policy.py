from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.db.models import ContentCandidate
from app.schemas.editorial_approval import (
    EditorialApprovalCandidateView,
    EditorialApprovalRunResult,
    EditorialApprovalStatusView,
)
from app.utils.time import utcnow


AUTOAPPROVABLE_CONTENT_TYPES = (
    ContentType.MATCH_RESULT,
    ContentType.STANDINGS,
    ContentType.PREVIEW,
    ContentType.RANKING,
)
MANUAL_REVIEW_CONTENT_TYPES = (
    ContentType.STANDINGS_EVENT,
    ContentType.FORM_RANKING,
    ContentType.FORM_EVENT,
    ContentType.FEATURED_MATCH_PREVIEW,
    ContentType.FEATURED_MATCH_EVENT,
    ContentType.STAT_NARRATIVE,
    ContentType.METRIC_NARRATIVE,
    ContentType.VIRAL_STORY,
)


def _excerpt(text: str, limit: int = 100) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


class EditorialApprovalPolicyService:
    def __init__(self, session: Session, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def status(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 200,
    ) -> EditorialApprovalStatusView:
        rows = self._pending_drafts(reference_date=reference_date, limit=limit)
        autoapprovable_count = sum(1 for row in rows if self._evaluate(row).autoapprovable)
        return EditorialApprovalStatusView(
            enabled=True,
            autoapprovable_content_types=list(AUTOAPPROVABLE_CONTENT_TYPES),
            manual_review_content_types=list(MANUAL_REVIEW_CONTENT_TYPES),
            drafts_found=len(rows),
            autoapprovable_count=autoapprovable_count,
            manual_review_count=len(rows) - autoapprovable_count,
        )

    def autoapprove(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 200,
        dry_run: bool = False,
    ) -> EditorialApprovalRunResult:
        rows = self._pending_drafts(reference_date=reference_date, limit=limit)
        result_rows: list[EditorialApprovalCandidateView] = []
        autoapprovable_count = 0
        autoapproved_count = 0
        timestamp = utcnow()

        for row in rows:
            view = self._evaluate(row)
            if view.autoapprovable:
                autoapprovable_count += 1
                if not dry_run:
                    row.status = str(ContentCandidateStatus.APPROVED)
                    row.reviewed_at = timestamp
                    row.approved_at = timestamp
                    row.published_at = None
                    row.rejection_reason = None
                    row.autoapproved = True
                    row.autoapproved_at = timestamp
                    row.autoapproval_reason = view.policy_reason
                    self.session.add(row)
                    self.session.flush()
                    view = self._row_to_view(row, autoapprovable=True, policy_reason=view.policy_reason)
                autoapproved_count += 1
            result_rows.append(view)

        return EditorialApprovalRunResult(
            dry_run=dry_run,
            reference_date=reference_date,
            drafts_found=len(rows),
            autoapprovable_count=autoapprovable_count,
            autoapproved_count=autoapproved_count,
            manual_review_count=len(rows) - autoapprovable_count,
            rows=result_rows,
        )

    def _evaluate(self, candidate: ContentCandidate) -> EditorialApprovalCandidateView:
        autoapprovable = False
        policy_reason = "manual_review_policy"
        status = ContentCandidateStatus(candidate.status)
        if status != ContentCandidateStatus.DRAFT:
            policy_reason = f"status_not_draft:{status}"
        elif candidate.reviewed_at is not None:
            policy_reason = "already_reviewed"
        elif not candidate.text_draft.strip():
            policy_reason = "text_draft_empty"
        elif candidate.quality_check_passed is False or (candidate.quality_check_errors or []):
            policy_reason = "quality_errors_present"
        else:
            content_type = ContentType(candidate.content_type)
            if content_type in AUTOAPPROVABLE_CONTENT_TYPES:
                autoapprovable = True
                policy_reason = "policy_autoapprove_safe_type"
            elif content_type in MANUAL_REVIEW_CONTENT_TYPES:
                policy_reason = "manual_review_policy"
            else:
                policy_reason = "content_type_not_configured"
        return self._row_to_view(candidate, autoapprovable=autoapprovable, policy_reason=policy_reason)

    def _row_to_view(
        self,
        candidate: ContentCandidate,
        *,
        autoapprovable: bool,
        policy_reason: str,
    ) -> EditorialApprovalCandidateView:
        return EditorialApprovalCandidateView(
            id=candidate.id,
            competition_slug=candidate.competition_slug,
            content_type=ContentType(candidate.content_type),
            priority=candidate.priority,
            status=ContentCandidateStatus(candidate.status),
            autoapprovable=autoapprovable,
            policy_reason=policy_reason,
            autoapproved=candidate.autoapproved,
            autoapproved_at=candidate.autoapproved_at,
            autoapproval_reason=candidate.autoapproval_reason,
            created_at=candidate.created_at,
            excerpt=_excerpt(candidate.text_draft),
        )

    def _pending_drafts(
        self,
        *,
        reference_date: date | None,
        limit: int,
    ) -> list[ContentCandidate]:
        query = select(ContentCandidate).where(
            ContentCandidate.status == str(ContentCandidateStatus.DRAFT),
            ContentCandidate.reviewed_at.is_(None),
        )
        if reference_date is not None:
            start_utc, end_utc = self._day_bounds(reference_date)
            query = query.where(
                ContentCandidate.created_at >= start_utc,
                ContentCandidate.created_at < end_utc,
            )
        query = query.order_by(
            ContentCandidate.priority.desc(),
            case((ContentCandidate.scheduled_at.is_(None), 1), else_=0),
            ContentCandidate.scheduled_at.asc(),
            ContentCandidate.created_at.asc(),
        ).limit(limit)
        return self.session.execute(query).scalars().all()

    def _day_bounds(self, target_date: date) -> tuple[datetime, datetime]:
        start_local = datetime.combine(target_date, time.min, tzinfo=ZoneInfo(self.settings.timezone))
        end_local = start_local + timedelta(days=1)
        return (
            start_local.astimezone(timezone.utc),
            end_local.astimezone(timezone.utc),
        )
