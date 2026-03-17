from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.enums import ContentCandidateStatus
from app.db.models import ContentCandidate
from app.schemas.draft_temp import DraftTempCandidateView, DraftTempSnapshot, DraftTempSummary
from app.utils.time import utcnow

_CAPACITY_ERROR_PREFIX = "capacity_deferred:"


def _usable_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = text.strip()
    return normalized or None


def _excerpt(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


class DraftTempService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def build_snapshot(
        self,
        *,
        limit: int = 200,
        include_rejected: bool = False,
    ) -> DraftTempSnapshot:
        query = select(ContentCandidate)
        if not include_rejected:
            query = query.where(ContentCandidate.status != str(ContentCandidateStatus.REJECTED))
        status_order = case(
            (ContentCandidate.status == str(ContentCandidateStatus.DRAFT), 0),
            (ContentCandidate.status == str(ContentCandidateStatus.APPROVED), 1),
            (ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED), 2),
            (ContentCandidate.status == str(ContentCandidateStatus.REJECTED), 3),
            else_=99,
        )
        query = query.order_by(
            status_order,
            ContentCandidate.priority.desc(),
            ContentCandidate.created_at.desc(),
            ContentCandidate.id.desc(),
        ).limit(limit)
        rows = self.session.execute(query).scalars().all()
        return DraftTempSnapshot(
            generated_at=utcnow(),
            source="content_candidates",
            limit=limit,
            include_rejected=include_rejected,
            summary=self._summary(included_rows=len(rows)),
            rows=[self._row_to_view(row) for row in rows],
        )

    def _summary(self, *, included_rows: int) -> DraftTempSummary:
        counts = {
            status: count
            for status, count in self.session.execute(
                select(ContentCandidate.status, func.count())
                .group_by(ContentCandidate.status)
                .order_by(ContentCandidate.status)
            ).all()
        }
        scheduled_pending_count = int(
            self.session.scalar(
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
            )
            or 0
        )
        exported_count = int(
            self.session.scalar(
                select(func.count())
                .select_from(ContentCandidate)
                .where(ContentCandidate.external_publication_ref.is_not(None))
            )
            or 0
        )
        pending_rows = self.session.execute(
            select(ContentCandidate.external_publication_error)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
                func.length(func.trim(ContentCandidate.text_draft)) > 0,
            )
        ).scalars().all()
        capacity_deferred_count = sum(
            1 for error in pending_rows if self._is_capacity_deferred_error_text(str(error or ""))
        )
        failed_export_count = sum(
            1 for error in pending_rows if error and not self._is_capacity_deferred_error_text(str(error))
        )
        total_candidates = sum(counts.values())
        rejected_count = int(counts.get(str(ContentCandidateStatus.REJECTED), 0))
        return DraftTempSummary(
            total_candidates=total_candidates,
            active_candidates=total_candidates - rejected_count,
            included_rows=included_rows,
            draft_count=int(counts.get(str(ContentCandidateStatus.DRAFT), 0)),
            approved_count=int(counts.get(str(ContentCandidateStatus.APPROVED), 0)),
            rejected_count=rejected_count,
            published_count=int(counts.get(str(ContentCandidateStatus.PUBLISHED), 0)),
            scheduled_pending_count=scheduled_pending_count,
            pending_export_count=len(pending_rows),
            exported_count=exported_count,
            failed_export_count=failed_export_count,
            capacity_deferred_count=capacity_deferred_count,
        )

    def _row_to_view(self, row: ContentCandidate) -> DraftTempCandidateView:
        selected_text, selected_text_source = self._selected_text(row)
        return DraftTempCandidateView(
            id=row.id,
            competition_slug=row.competition_slug,
            content_type=row.content_type,
            priority=row.priority,
            status=row.status,
            source_summary_hash=row.source_summary_hash,
            scheduled_at=row.scheduled_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            reviewed_at=row.reviewed_at,
            approved_at=row.approved_at,
            published_at=row.published_at,
            external_publication_ref=row.external_publication_ref,
            external_channel=row.external_channel,
            external_exported_at=row.external_exported_at,
            external_publication_error=row.external_publication_error,
            quality_check_passed=row.quality_check_passed,
            quality_check_errors=list(row.quality_check_errors or []),
            has_formatted=_usable_text(row.formatted_text) is not None,
            has_rewrite=_usable_text(row.rewritten_text) is not None,
            selected_text_source=selected_text_source,
            selected_text=selected_text,
            excerpt=_excerpt(selected_text),
            text_draft=row.text_draft,
            formatted_text=row.formatted_text,
            rewritten_text=row.rewritten_text,
            payload_json=row.payload_json or {},
        )

    def _selected_text(self, row: ContentCandidate) -> tuple[str, str]:
        rewrite_text = _usable_text(row.rewritten_text)
        if rewrite_text is not None:
            return rewrite_text, "rewritten_text"
        formatted_text = _usable_text(row.formatted_text)
        if formatted_text is not None:
            return formatted_text, "formatted_text"
        draft_text = _usable_text(row.text_draft)
        if draft_text is not None:
            return draft_text, "text_draft"
        return "", "empty"

    def _is_capacity_deferred_error_text(self, error: str) -> bool:
        normalized = error.strip().upper()
        if not normalized:
            return False
        if normalized.startswith(_CAPACITY_ERROR_PREFIX.upper()):
            return True
        return "MONETIZATION_ERROR" in normalized
