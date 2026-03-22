from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.db.models import ContentCandidate
from app.schemas.editorial_approval import (
    EditorialApprovalCandidateView,
    EditorialApprovalRunResult,
    EditorialApprovalStatusView,
)
from app.services.editorial_candidate_window import EditorialCandidateWindowService
from app.services.editorial_quality_checks import EditorialQualityChecksService
from app.services.story_importance import StoryImportanceService
from app.utils.time import utcnow


AUTOAPPROVABLE_CONTENT_TYPES = (
    ContentType.RESULTS_ROUNDUP,
    ContentType.STANDINGS_ROUNDUP,
    ContentType.PREVIEW,
    ContentType.RANKING,
)
CONDITIONAL_AUTOAPPROVABLE_CONTENT_TYPES: tuple[ContentType, ...] = ()
MANUAL_REVIEW_CONTENT_TYPES = (
    ContentType.MATCH_RESULT,
    ContentType.STANDINGS,
    ContentType.FORM_RANKING,
    ContentType.FEATURED_MATCH_PREVIEW,
    ContentType.FEATURED_MATCH_EVENT,
    ContentType.STANDINGS_EVENT,
    ContentType.FORM_EVENT,
    ContentType.VIRAL_STORY,
    ContentType.STAT_NARRATIVE,
    ContentType.METRIC_NARRATIVE,
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
        self.window_service = EditorialCandidateWindowService(session, settings=self.settings)
        self.quality_service = EditorialQualityChecksService(session, settings=self.settings)
        self.story_service = StoryImportanceService(session, settings=self.settings)

    def status(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 200,
    ) -> EditorialApprovalStatusView:
        rows = self._pending_drafts(reference_date=reference_date, limit=limit)
        quality_snapshot = self._quality_snapshot(rows)
        views = self._evaluate_rows(rows, quality_snapshot=quality_snapshot)
        autoapprovable_count = sum(1 for view in views if view.autoapprovable)
        return EditorialApprovalStatusView(
            enabled=True,
            autoapprovable_content_types=list(AUTOAPPROVABLE_CONTENT_TYPES),
            conditional_autoapprovable_content_types=list(CONDITIONAL_AUTOAPPROVABLE_CONTENT_TYPES),
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
        quality_snapshot = self._quality_snapshot(rows)
        evaluated_rows = {
            view.id: view for view in self._evaluate_rows(rows, quality_snapshot=quality_snapshot)
        }
        result_rows: list[EditorialApprovalCandidateView] = []
        autoapprovable_count = 0
        autoapproved_count = 0
        timestamp = utcnow()

        for row in rows:
            view = evaluated_rows[row.id]
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
                    view = self._row_to_view(
                        row,
                        autoapprovable=True,
                        policy_reason=view.policy_reason,
                        importance_score=view.importance_score,
                        priority_bucket=view.priority_bucket,
                        importance_reasoning=view.importance_reasoning,
                    )
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

    def candidate_ids_for_quality_precheck(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 200,
    ) -> list[int]:
        rows = self._pending_drafts(reference_date=reference_date, limit=limit)
        return [row.id for row in rows if self._is_potential_autoapprovable(row)]

    def _evaluate_rows(
        self,
        candidates: list[ContentCandidate],
        *,
        quality_snapshot: dict[int, tuple[bool, list[str]]] | None = None,
    ) -> list[EditorialApprovalCandidateView]:
        views_by_id: dict[int, EditorialApprovalCandidateView] = {}
        conditional_candidates: list[ContentCandidate] = []
        for candidate in candidates:
            autoapprovable, policy_reason = self._base_policy(
                candidate,
                quality_snapshot=quality_snapshot,
            )
            if policy_reason == "story_importance_pending":
                conditional_candidates.append(candidate)
                continue
            views_by_id[candidate.id] = self._row_to_view(
                candidate,
                autoapprovable=autoapprovable,
                policy_reason=policy_reason,
            )

        decisions = self.story_service.select_automatic_narratives(conditional_candidates)
        for candidate in conditional_candidates:
            decision = decisions[candidate.id]
            views_by_id[candidate.id] = self._row_to_view(
                candidate,
                autoapprovable=decision.allowed,
                policy_reason=(
                    "policy_autoapprove_story_importance"
                    if decision.allowed
                    else decision.reason
                ),
                importance_score=decision.importance_score,
                priority_bucket=decision.priority_bucket,
                importance_reasoning=decision.importance_reasoning,
            )
        return [views_by_id[candidate.id] for candidate in candidates]

    def _base_policy(
        self,
        candidate: ContentCandidate,
        *,
        quality_snapshot: dict[int, tuple[bool, list[str]]] | None = None,
    ) -> tuple[bool, str]:
        status = ContentCandidateStatus(candidate.status)
        quality_passed, quality_errors = self._quality_state(
            candidate,
            quality_snapshot=quality_snapshot,
        )
        if status != ContentCandidateStatus.DRAFT:
            return False, f"status_not_draft:{status}"
        elif candidate.reviewed_at is not None:
            return False, "already_reviewed"
        elif not candidate.text_draft.strip():
            return False, "text_draft_empty"
        elif quality_passed is False or quality_errors:
            return False, "quality_errors_present"
        else:
            content_type = ContentType(candidate.content_type)
            if content_type in AUTOAPPROVABLE_CONTENT_TYPES:
                return True, "policy_autoapprove_safe_type"
            if content_type in CONDITIONAL_AUTOAPPROVABLE_CONTENT_TYPES:
                return False, "story_importance_pending"
            elif content_type in MANUAL_REVIEW_CONTENT_TYPES:
                return False, "manual_review_policy"
            else:
                return False, "content_type_not_configured"

    def _is_potential_autoapprovable(self, candidate: ContentCandidate) -> bool:
        status = ContentCandidateStatus(candidate.status)
        if status != ContentCandidateStatus.DRAFT:
            return False
        if candidate.reviewed_at is not None:
            return False
        if not candidate.text_draft.strip():
            return False
        content_type = ContentType(candidate.content_type)
        return (
            content_type in AUTOAPPROVABLE_CONTENT_TYPES
            or content_type in CONDITIONAL_AUTOAPPROVABLE_CONTENT_TYPES
        )

    def _quality_snapshot(
        self,
        rows: list[ContentCandidate],
    ) -> dict[int, tuple[bool, list[str]]]:
        candidate_ids = [row.id for row in rows if self._is_potential_autoapprovable(row)]
        if not candidate_ids:
            return {}
        batch = self.quality_service.check_candidates(
            candidate_ids,
            dry_run=True,
            require_published=False,
        )
        return {
            row.id: (row.passed, list(row.errors))
            for row in batch.rows
        }

    def _quality_state(
        self,
        candidate: ContentCandidate,
        *,
        quality_snapshot: dict[int, tuple[bool, list[str]]] | None,
    ) -> tuple[bool | None, list[str]]:
        if quality_snapshot is not None and candidate.id in quality_snapshot:
            passed, errors = quality_snapshot[candidate.id]
            return passed, list(errors)
        return candidate.quality_check_passed, list(candidate.quality_check_errors or [])

    def _row_to_view(
        self,
        candidate: ContentCandidate,
        *,
        autoapprovable: bool,
        policy_reason: str,
        importance_score: int | None = None,
        priority_bucket: str | None = None,
        importance_reasoning: list[str] | None = None,
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
            importance_score=importance_score,
            priority_bucket=priority_bucket,
            importance_reasoning=list(importance_reasoning or []),
            created_at=candidate.created_at,
            excerpt=_excerpt(candidate.text_draft),
        )

    def _pending_drafts(
        self,
        *,
        reference_date: date | None,
        limit: int,
    ) -> list[ContentCandidate]:
        selected_date = reference_date or datetime.now(ZoneInfo(self.settings.timezone)).date()
        query = select(ContentCandidate).where(
            ContentCandidate.status == str(ContentCandidateStatus.DRAFT),
            ContentCandidate.reviewed_at.is_(None),
        )
        if selected_date is not None:
            start_utc, end_utc = self._day_bounds(selected_date)
            query = query.where(
                or_(
                    and_(
                        ContentCandidate.created_at >= start_utc,
                        ContentCandidate.created_at < end_utc,
                    ),
                    ContentCandidate.payload_json["reference_date"].as_string() == selected_date.isoformat(),
                ),
            )
        query = query.order_by(
            ContentCandidate.priority.desc(),
            case((ContentCandidate.scheduled_at.is_(None), 1), else_=0),
            ContentCandidate.scheduled_at.asc(),
            ContentCandidate.created_at.asc(),
        ).limit(limit)
        rows = self.session.execute(query).scalars().all()
        return [
            row
            for row in rows
            if self.window_service.matches_release_window(row, reference_date=selected_date)
        ]

    def _day_bounds(self, target_date: date) -> tuple[datetime, datetime]:
        start_local = datetime.combine(target_date, time.min, tzinfo=ZoneInfo(self.settings.timezone))
        end_local = start_local + timedelta(days=1)
        return (
            start_local.astimezone(timezone.utc),
            end_local.astimezone(timezone.utc),
        )
