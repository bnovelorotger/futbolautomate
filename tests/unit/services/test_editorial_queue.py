from __future__ import annotations

import pytest

from app.core.enums import ContentCandidateStatus
from app.core.exceptions import InvalidStateTransitionError
from app.services.editorial_queue import EditorialQueueService


def test_editorial_queue_validates_allowed_transitions() -> None:
    service = EditorialQueueService.__new__(EditorialQueueService)

    EditorialQueueService._validate_transition(
        service,
        ContentCandidateStatus.DRAFT,
        ContentCandidateStatus.APPROVED,
    )
    EditorialQueueService._validate_transition(
        service,
        ContentCandidateStatus.APPROVED,
        ContentCandidateStatus.PUBLISHED,
    )
    EditorialQueueService._validate_transition(
        service,
        ContentCandidateStatus.REJECTED,
        ContentCandidateStatus.DRAFT,
    )


def test_editorial_queue_rejects_invalid_transitions() -> None:
    service = EditorialQueueService.__new__(EditorialQueueService)

    with pytest.raises(InvalidStateTransitionError):
        EditorialQueueService._validate_transition(
            service,
            ContentCandidateStatus.DRAFT,
            ContentCandidateStatus.PUBLISHED,
        )

    with pytest.raises(InvalidStateTransitionError):
        EditorialQueueService._validate_transition(
            service,
            ContentCandidateStatus.PUBLISHED,
            ContentCandidateStatus.DRAFT,
        )
