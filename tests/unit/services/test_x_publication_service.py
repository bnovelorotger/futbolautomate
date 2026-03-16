from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.channels.x.auth import XAuthError
from app.channels.x.client import XApiError
from app.channels.x.schemas import XPublishResponse
from app.core.exceptions import InvalidStateTransitionError
from app.db.base import Base
from app.db.models import Competition, ContentCandidate
from app.services.x_publication_service import (
    XPublicationService,
    is_candidate_eligible_for_x,
)


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def seed_candidates(session: Session) -> None:
    now = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    competition = Competition(
        code="segunda_rfef_g3_baleares",
        name="2a RFEF Grupo 3",
        normalized_name="2a rfef grupo 3",
        category_level=4,
        gender="male",
        region="Baleares",
        country="Spain",
        federation="RFEF",
        source_name="futbolme",
        source_competition_id="3059",
    )
    session.add(competition)
    session.flush()
    session.add_all(
        [
            ContentCandidate(
                id=1,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="match_result",
                priority=99,
                text_draft="RESULTADO FINAL\n\nTorrent CF 1-0 UE Porreres",
                payload_json={},
                source_summary_hash="hash-1",
                scheduled_at=now,
                status="published",
                reviewed_at=now,
                approved_at=now,
                published_at=now,
                rejection_reason=None,
                external_publication_ref=None,
                external_channel=None,
                external_exported_at=None,
                external_publication_timestamp=None,
                external_publication_attempted_at=None,
                external_publication_error=None,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=2,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="standings",
                priority=80,
                text_draft="CLASIFICACION\n\n1. UE Sant Andreu - 54 pts",
                payload_json={},
                source_summary_hash="hash-2",
                scheduled_at=now,
                status="published",
                reviewed_at=now,
                approved_at=now,
                published_at=now,
                rejection_reason=None,
                external_publication_ref="tweet-2",
                external_channel="x",
                external_exported_at=now,
                external_publication_timestamp=now,
                external_publication_attempted_at=now,
                external_publication_error=None,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=3,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="preview",
                priority=90,
                text_draft="PREVIA",
                payload_json={},
                source_summary_hash="hash-3",
                scheduled_at=now,
                status="approved",
                reviewed_at=now,
                approved_at=now,
                published_at=None,
                rejection_reason=None,
                external_publication_ref=None,
                external_channel=None,
                external_exported_at=None,
                external_publication_timestamp=None,
                external_publication_attempted_at=None,
                external_publication_error=None,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=4,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="ranking",
                priority=70,
                text_draft="   ",
                payload_json={},
                source_summary_hash="hash-4",
                scheduled_at=now,
                status="published",
                reviewed_at=now,
                approved_at=now,
                published_at=now,
                rejection_reason=None,
                external_publication_ref=None,
                external_channel=None,
                external_exported_at=None,
                external_publication_timestamp=None,
                external_publication_attempted_at=None,
                external_publication_error=None,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()


def test_x_publication_service_eligibility_filter() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        candidate_1 = session.get(ContentCandidate, 1)
        candidate_2 = session.get(ContentCandidate, 2)
        candidate_3 = session.get(ContentCandidate, 3)
        candidate_4 = session.get(ContentCandidate, 4)

        assert candidate_1 is not None
        assert candidate_2 is not None
        assert candidate_3 is not None
        assert candidate_4 is not None
        assert is_candidate_eligible_for_x(candidate_1) is True
        assert is_candidate_eligible_for_x(candidate_2) is False
        assert is_candidate_eligible_for_x(candidate_3) is False
        assert is_candidate_eligible_for_x(candidate_4) is False
    finally:
        session.close()


def test_x_publication_service_lists_and_publishes_successfully() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.publish_text.return_value = XPublishResponse(
            post_id="tweet-1",
            text="RESULTADO FINAL",
            published_at=datetime(2026, 3, 15, 10, 5, tzinfo=timezone.utc),
            raw_response={"data": {"id": "tweet-1"}},
            dry_run=False,
        )
        auth_service = Mock()
        auth_service.get_valid_user_access_token.return_value = "user-access-token"
        service = XPublicationService(session, publisher=publisher, auth_service=auth_service)

        pending = service.list_pending(limit=10)
        result = service.publish_candidate(1, dry_run=False)
        session.commit()

        assert [row.id for row in pending] == [1]
        assert result.candidate.external_publication_ref == "tweet-1"
        assert result.candidate.external_publication_timestamp is not None
        assert result.candidate.external_publication_error is None
        assert session.get(ContentCandidate, 1).external_publication_ref == "tweet-1"
        assert session.get(ContentCandidate, 1).external_channel == "x"
        assert session.get(ContentCandidate, 1).external_exported_at is not None
        publisher.publish_text.assert_called_once()
    finally:
        session.close()


def test_x_publication_service_records_api_error_without_ref() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.publish_text.side_effect = XApiError("rate limit")
        auth_service = Mock()
        auth_service.get_valid_user_access_token.return_value = "user-access-token"
        service = XPublicationService(session, publisher=publisher, auth_service=auth_service)

        with pytest.raises(XApiError):
            service.publish_candidate(1, dry_run=False)
        session.commit()

        candidate = session.get(ContentCandidate, 1)
        assert candidate.external_publication_ref is None
        assert candidate.external_publication_attempted_at is not None
        assert candidate.external_publication_error == "rate limit"
    finally:
        session.close()


def test_x_publication_service_supports_dry_run_without_persistence() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.publish_text.return_value = XPublishResponse(
            post_id="dry-run",
            text="RESULTADO FINAL",
            published_at=datetime(2026, 3, 15, 10, 5, tzinfo=timezone.utc),
            raw_response={"dry_run": True},
            dry_run=True,
        )
        auth_service = Mock()
        service = XPublicationService(session, publisher=publisher, auth_service=auth_service)

        result = service.publish_candidate(1, dry_run=True)
        session.commit()

        candidate = session.get(ContentCandidate, 1)
        assert result.dry_run is True
        assert candidate.external_publication_ref is None
        assert candidate.external_publication_attempted_at is None
        auth_service.get_valid_user_access_token.assert_not_called()
    finally:
        session.close()


def test_x_publication_service_publish_pending_dry_run() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        publisher.publish_text.return_value = XPublishResponse(
            post_id="dry-run",
            text="RESULTADO FINAL",
            published_at=datetime(2026, 3, 15, 10, 5, tzinfo=timezone.utc),
            raw_response={"dry_run": True},
            dry_run=True,
        )
        auth_service = Mock()
        service = XPublicationService(session, publisher=publisher, auth_service=auth_service)

        result = service.publish_pending(limit=10, dry_run=True)
        session.commit()

        assert result.dry_run is True
        assert result.published_count == 1
        assert [row.id for row in result.rows] == [1]
        assert session.get(ContentCandidate, 1).external_publication_ref is None
    finally:
        session.close()


def test_x_publication_service_rejects_invalid_states_and_config_errors() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        publisher = Mock()
        auth_service = Mock()
        auth_service.get_valid_user_access_token.side_effect = XAuthError("no hay token de usuario")
        service = XPublicationService(session, publisher=publisher, auth_service=auth_service)

        with pytest.raises(InvalidStateTransitionError):
            service.publish_candidate(3, dry_run=False)

        with pytest.raises(InvalidStateTransitionError):
            service.publish_candidate(2, dry_run=False)

        with pytest.raises(InvalidStateTransitionError):
            service.publish_candidate(4, dry_run=False)

        with pytest.raises(XAuthError):
            service.publish_candidate(1, dry_run=False)
        assert session.get(ContentCandidate, 1).external_publication_attempted_at is not None
        assert session.get(ContentCandidate, 1).external_publication_error == "no hay token de usuario"
    finally:
        session.close()
