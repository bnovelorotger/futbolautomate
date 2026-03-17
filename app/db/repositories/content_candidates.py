from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.enums import ContentCandidateStatus
from app.db.models import ContentCandidate
from app.db.repositories.base import BaseRepository


def _normalized_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ContentCandidateRepository(BaseRepository[ContentCandidate]):
    def get_by_hash(
        self,
        competition_slug: str,
        content_type: str,
        source_summary_hash: str,
    ) -> ContentCandidate | None:
        return self.session.scalar(
            select(ContentCandidate).where(
                ContentCandidate.competition_slug == competition_slug,
                ContentCandidate.content_type == content_type,
                ContentCandidate.source_summary_hash == source_summary_hash,
            )
        )

    def upsert(self, payload: dict) -> tuple[ContentCandidate, bool, bool]:
        item = self.get_by_hash(
            competition_slug=payload["competition_slug"],
            content_type=payload["content_type"],
            source_summary_hash=payload["source_summary_hash"],
        )
        if item is None:
            item = ContentCandidate(**payload)
            self.session.add(item)
            self.session.flush()
            return item, True, False

        if item.status != ContentCandidateStatus.DRAFT:
            return item, False, False

        updated = False
        should_reset_rewrite = False
        for field in ("priority", "text_draft", "formatted_text", "payload_json", "scheduled_at"):
            value = payload.get(field)
            current_value = getattr(item, field)
            if field == "scheduled_at":
                if current_value is not None:
                    continue
                changed = _normalized_datetime(current_value) != _normalized_datetime(value)
            else:
                changed = current_value != value
            if changed:
                setattr(item, field, value)
                updated = True
                if field in {"text_draft", "formatted_text", "payload_json"}:
                    should_reset_rewrite = True
        if should_reset_rewrite:
            item.rewritten_text = None
            item.rewrite_status = None
            item.rewrite_model = None
            item.rewrite_timestamp = None
            item.rewrite_error = None
            item.autoapproved = None
            item.autoapproved_at = None
            item.autoapproval_reason = None
            item.quality_check_passed = None
            item.quality_check_errors = None
            item.quality_checked_at = None
        if updated:
            self.session.add(item)
            self.session.flush()
        return item, False, updated

    def get(self, candidate_id: int) -> ContentCandidate | None:
        return self.session.get(ContentCandidate, candidate_id)
