from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.enums import ContentCandidateStatus
from app.core.exceptions import InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.services.publication_dispatcher import (
    is_candidate_ready_for_dispatch,
    validate_candidate_can_publish,
)


def build_candidate(
    *,
    status: str,
    scheduled_at: datetime | None,
    published_at: datetime | None = None,
    content_type: str = "match_result",
) -> ContentCandidate:
    now = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)
    return ContentCandidate(
        id=1,
        competition_slug="tercera_rfef_g11",
        content_type=content_type,
        priority=99,
        text_draft="RESULTADO FINAL",
        payload_json={},
        source_summary_hash="hash-1",
        scheduled_at=scheduled_at,
        status=status,
        reviewed_at=None,
        approved_at=now if status == str(ContentCandidateStatus.APPROVED) else None,
        published_at=published_at,
        rejection_reason=None,
        external_publication_ref=None,
        created_at=now,
        updated_at=now,
    )


def test_publication_dispatcher_detects_ready_candidates() -> None:
    now = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)

    due = build_candidate(status="approved", scheduled_at=now)
    unscheduled = build_candidate(status="approved", scheduled_at=None)
    future = build_candidate(
        status="approved",
        scheduled_at=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
    )
    future_preview = build_candidate(
        status="approved",
        scheduled_at=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
        content_type="preview",
    )
    draft = build_candidate(status="draft", scheduled_at=now)

    assert is_candidate_ready_for_dispatch(due, now, include_unscheduled=False) is True
    assert is_candidate_ready_for_dispatch(unscheduled, now, include_unscheduled=False) is False
    assert is_candidate_ready_for_dispatch(unscheduled, now, include_unscheduled=True) is True
    assert is_candidate_ready_for_dispatch(future, now, include_unscheduled=True) is False
    assert is_candidate_ready_for_dispatch(future_preview, now, include_unscheduled=True) is True
    assert is_candidate_ready_for_dispatch(draft, now, include_unscheduled=True) is False


def test_publication_dispatcher_rejects_invalid_publish_states() -> None:
    now = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)

    validate_candidate_can_publish(build_candidate(status="approved", scheduled_at=now))

    with pytest.raises(InvalidStateTransitionError):
        validate_candidate_can_publish(build_candidate(status="draft", scheduled_at=now))

    with pytest.raises(InvalidStateTransitionError):
        validate_candidate_can_publish(
            build_candidate(
                status="published",
                scheduled_at=now,
                published_at=now,
            )
        )
