from __future__ import annotations

from datetime import date, datetime, time, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.channels.x.auth import XAuthError
from app.channels.x.client import XApiError
from app.channels.x.schemas import XPublishResponse
from app.core.exceptions import InvalidStateTransitionError
from app.db.base import Base
from app.db.models import Competition, ContentCandidate, Match
from app.services.x_publication_scheduler import XPublicationScheduler
from app.services.x_publication_service import (
    XPublicationService,
    is_candidate_eligible_for_x,
)
from tests.unit.services.service_test_support import build_settings


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def build_scheduler(*, current_time: datetime) -> XPublicationScheduler:
    return XPublicationScheduler(
        settings=build_settings(timezone="Europe/Madrid"),
        now_provider=lambda: current_time,
    )


def build_results_payload(*, reference_date: str, match_date: str, round_name: str = "Jornada 26") -> dict:
    return {
        "reference_date": reference_date,
        "source_payload": {
            "reference_date": reference_date,
            "selected_matches_count": 1,
            "omitted_matches_count": 0,
            "group_label": round_name,
            "matches": [
                {
                    "round_name": round_name,
                    "match_date": match_date,
                    "home_team": "Torrent CF",
                    "away_team": "UE Porreres",
                    "home_score": 1,
                    "away_score": 0,
                }
            ],
        },
    }


def build_preview_payload(*, reference_date: str, match_date: str, round_name: str = "Jornada 27") -> dict:
    return {
        "reference_date": reference_date,
        "source_payload": {
            "reference_date": reference_date,
            "featured_match": {
                "round_name": round_name,
                "match_date": match_date,
                "home_team": "Torrent CF",
                "away_team": "UE Porreres",
            },
            "teams": ["Torrent CF", "UE Porreres"],
        },
    }


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
            Match(
                external_id="m-current",
                source_name="futbolme",
                source_url="https://example.com/m-current",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                round_name="Jornada 26",
                raw_match_date="2026-03-15",
                raw_match_time="12:00",
                match_date=date(2026, 3, 15),
                match_time=time(12, 0),
                kickoff_datetime=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
                home_team_raw="Torrent CF",
                away_team_raw="UE Porreres",
                home_score=1,
                away_score=0,
                status="finished",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=now,
                content_hash="m-current",
                extra_data={},
            ),
            Match(
                external_id="m-upcoming",
                source_name="futbolme",
                source_url="https://example.com/m-upcoming",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                round_name="Jornada 27",
                raw_match_date="2026-03-20",
                raw_match_time="18:00",
                match_date=date(2026, 3, 20),
                match_time=time(18, 0),
                kickoff_datetime=datetime(2026, 3, 20, 18, 0, tzinfo=timezone.utc),
                home_team_raw="Torrent CF",
                away_team_raw="UE Porreres",
                home_score=None,
                away_score=None,
                status="scheduled",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=now,
                content_hash="m-upcoming",
                extra_data={},
            ),
        ]
    )
    session.add_all(
        [
            ContentCandidate(
                id=1,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="results_roundup",
                priority=99,
                text_draft="RESULTADO FINAL\n\nTorrent CF 1-0 UE Porreres",
                formatted_text="Resultado | Torrent CF 1-0 UE Porreres #2aRFEF",
                rewritten_text="Torrent CF 1-0 UE Porreres. Final en Segunda RFEF balear.",
                payload_json=build_results_payload(
                    reference_date="2026-03-16",
                    match_date="2026-03-15",
                ),
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
                content_type="standings_roundup",
                priority=80,
                text_draft="CLASIFICACION\n\n1. UE Sant Andreu - 54 pts",
                payload_json={
                    "reference_date": "2026-03-16",
                    "source_payload": {
                        "reference_date": "2026-03-16",
                        "rows": [{"team": "Torrent CF", "points": 54, "position": 1}],
                        "selected_rows_count": 1,
                    },
                },
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
                content_type="featured_match_preview",
                priority=90,
                text_draft="PREVIA",
                payload_json=build_preview_payload(
                    reference_date="2026-03-20",
                    match_date="2026-03-20",
                ),
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
                payload_json={"reference_date": "2026-03-16", "source_payload": {}},
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
        service = XPublicationService(
            session,
            publisher=publisher,
            auth_service=auth_service,
            scheduler=build_scheduler(current_time=datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))),
        )

        pending = service.list_pending(limit=10)
        result = service.publish_candidate(1, dry_run=False)
        session.commit()

        assert [row.id for row in pending] == [1]
        assert pending[0].selected_text_source == "rewritten_text"
        assert result.candidate.external_publication_ref == "tweet-1"
        assert result.candidate.external_publication_timestamp is not None
        assert result.candidate.external_publication_error is None
        assert session.get(ContentCandidate, 1).external_publication_ref == "tweet-1"
        assert session.get(ContentCandidate, 1).external_channel == "x"
        assert session.get(ContentCandidate, 1).external_exported_at is not None
        publisher.publish_text.assert_called_once_with(
            "Torrent CF 1-0 UE Porreres. Final en Segunda RFEF balear.",
            access_token="user-access-token",
            dry_run=False,
        )
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
        service = XPublicationService(
            session,
            publisher=publisher,
            auth_service=auth_service,
            scheduler=build_scheduler(current_time=datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))),
        )

        with pytest.raises(XApiError):
            service.publish_candidate(1, dry_run=False)
        session.commit()

        candidate = session.get(ContentCandidate, 1)
        assert candidate.external_publication_ref is None
        assert candidate.external_publication_attempted_at is not None
        assert candidate.external_publication_error == "rate limit"
        assert candidate.publication_attempts == 1
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
        service = XPublicationService(
            session,
            publisher=publisher,
            auth_service=auth_service,
            scheduler=build_scheduler(current_time=datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))),
        )

        result = service.publish_candidate(1, dry_run=True)
        session.commit()

        candidate = session.get(ContentCandidate, 1)
        assert result.dry_run is True
        assert result.candidate.selected_text_source == "rewritten_text"
        assert candidate.external_publication_ref is None
        assert candidate.external_publication_attempted_at is None
        auth_service.get_valid_user_access_token.assert_not_called()
        publisher.publish_text.assert_called_once_with(
            "Torrent CF 1-0 UE Porreres. Final en Segunda RFEF balear.",
            dry_run=True,
        )
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
        service = XPublicationService(
            session,
            publisher=publisher,
            auth_service=auth_service,
            scheduler=build_scheduler(current_time=datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))),
        )

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
        service = XPublicationService(
            session,
            publisher=publisher,
            auth_service=auth_service,
            scheduler=build_scheduler(current_time=datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))),
        )

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
        assert session.get(ContentCandidate, 1).publication_attempts == 1
    finally:
        session.close()


def test_x_publication_service_publish_pending_respects_schedule_and_retry_budget() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        now = datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        session.add_all(
            [
                ContentCandidate(
                    id=5,
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="results_roundup",
                    priority=95,
                    text_draft="SEGUNDO INTENTO",
                    payload_json=build_results_payload(
                        reference_date="2026-03-16",
                        match_date="2026-03-15",
                    ),
                    source_summary_hash="hash-5",
                    scheduled_at=now,
                    status="published",
                    reviewed_at=now,
                    approved_at=now,
                    published_at=now,
                    external_publication_error="rate limit",
                    publication_attempts=2,
                    created_at=now,
                    updated_at=now,
                ),
                ContentCandidate(
                    id=6,
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="results_roundup",
                    priority=94,
                    text_draft="NO MAS RETRIES",
                    payload_json=build_results_payload(
                        reference_date="2026-03-16",
                        match_date="2026-03-15",
                    ),
                    source_summary_hash="hash-6",
                    scheduled_at=now,
                    status="published",
                    reviewed_at=now,
                    approved_at=now,
                    published_at=now,
                    external_publication_error="rate limit",
                    publication_attempts=3,
                    created_at=now,
                    updated_at=now,
                ),
                ContentCandidate(
                    id=7,
                    competition_slug="segunda_rfef_g3_baleares",
                    content_type="featured_match_preview",
                    priority=93,
                    text_draft="VIERNES SOLO",
                    payload_json=build_preview_payload(
                        reference_date="2026-03-20",
                        match_date="2026-03-20",
                    ),
                    source_summary_hash="hash-7",
                    scheduled_at=now,
                    status="published",
                    reviewed_at=now,
                    approved_at=now,
                    published_at=now,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()

        publisher = Mock()
        publisher.publish_text.side_effect = [
            XPublishResponse(
                post_id="tweet-1",
                text="RESULTADO FINAL",
                published_at=datetime(2026, 3, 16, 9, 5, tzinfo=timezone.utc),
                raw_response={"data": {"id": "tweet-1"}},
                dry_run=False,
            ),
            XPublishResponse(
                post_id="tweet-5",
                text="SEGUNDO INTENTO",
                published_at=datetime(2026, 3, 16, 9, 6, tzinfo=timezone.utc),
                raw_response={"data": {"id": "tweet-5"}},
                dry_run=False,
            ),
        ]
        auth_service = Mock()
        auth_service.get_valid_user_access_token.return_value = "user-access-token"
        service = XPublicationService(
            session,
            publisher=publisher,
            auth_service=auth_service,
            scheduler=build_scheduler(current_time=now),
        )

        result = service.publish_pending(limit=10, dry_run=False)
        session.commit()

        assert [row.id for row in result.rows] == [1, 5]
        assert result.published_count == 2
        assert session.get(ContentCandidate, 5).external_publication_ref == "tweet-5"
        assert session.get(ContentCandidate, 5).publication_attempts == 3
        assert session.get(ContentCandidate, 6).external_publication_ref is None
        assert session.get(ContentCandidate, 6).publication_attempts == 3
        assert session.get(ContentCandidate, 7).external_publication_ref is None
    finally:
        session.close()


def test_x_publication_service_publish_candidates_respects_schedule_for_release_batches() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        friday_candidate_time = datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc)
        session.add(
            ContentCandidate(
                id=7,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="featured_match_preview",
                priority=93,
                text_draft="PREVIA DE VIERNES",
                payload_json=build_preview_payload(
                    reference_date="2026-03-20",
                    match_date="2026-03-20",
                ),
                source_summary_hash="hash-7",
                scheduled_at=friday_candidate_time,
                status="published",
                reviewed_at=friday_candidate_time,
                approved_at=friday_candidate_time,
                published_at=friday_candidate_time,
                created_at=friday_candidate_time,
                updated_at=friday_candidate_time,
            )
        )
        session.commit()

        publisher = Mock()
        publisher.publish_text.return_value = XPublishResponse(
            post_id="tweet-1",
            text="RESULTADO FINAL",
            published_at=datetime(2026, 3, 16, 9, 5, tzinfo=timezone.utc),
            raw_response={"data": {"id": "tweet-1"}},
            dry_run=False,
        )
        auth_service = Mock()
        auth_service.get_valid_user_access_token.return_value = "user-access-token"
        service = XPublicationService(
            session,
            publisher=publisher,
            auth_service=auth_service,
            scheduler=build_scheduler(current_time=datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))),
        )

        result = service.publish_candidates([1, 7], dry_run=False)
        session.commit()

        assert [row.id for row in result.rows] == [1]
        assert session.get(ContentCandidate, 1).external_publication_ref == "tweet-1"
        assert session.get(ContentCandidate, 7).external_publication_ref is None
    finally:
        session.close()


def test_x_publication_service_ignores_stale_candidates_from_previous_window() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        now = datetime(2026, 3, 16, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))
        competition = session.query(Competition).filter_by(code="segunda_rfef_g3_baleares").one()
        session.add(
            Match(
                external_id="m-old",
                source_name="futbolme",
                source_url="https://example.com/m-old",
                competition_id=competition.id,
                season="2025-26",
                group_name="Grupo 3",
                round_name="Jornada 25",
                raw_match_date="2026-03-08",
                raw_match_time="12:00",
                match_date=date(2026, 3, 8),
                match_time=time(12, 0),
                kickoff_datetime=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
                home_team_raw="Torrent CF",
                away_team_raw="UE Porreres",
                home_score=2,
                away_score=1,
                status="finished",
                venue=None,
                has_lineups=False,
                has_scorers=False,
                scraped_at=datetime(2026, 3, 8, 14, 0, tzinfo=timezone.utc),
                content_hash="m-old",
                extra_data={},
            )
        )
        session.add(
            ContentCandidate(
                id=8,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="results_roundup",
                priority=96,
                text_draft="RESULTADO VIEJO",
                payload_json=build_results_payload(
                    reference_date="2026-03-09",
                    match_date="2026-03-08",
                    round_name="Jornada 25",
                ),
                source_summary_hash="hash-8",
                scheduled_at=datetime(2026, 3, 8, 14, 0, tzinfo=timezone.utc),
                status="published",
                reviewed_at=datetime(2026, 3, 8, 14, 0, tzinfo=timezone.utc),
                approved_at=datetime(2026, 3, 8, 14, 0, tzinfo=timezone.utc),
                published_at=datetime(2026, 3, 8, 14, 0, tzinfo=timezone.utc),
                created_at=datetime(2026, 3, 8, 14, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 3, 8, 14, 0, tzinfo=timezone.utc),
            )
        )
        session.commit()

        publisher = Mock()
        publisher.publish_text.return_value = XPublishResponse(
            post_id="tweet-1",
            text="RESULTADO FINAL",
            published_at=datetime(2026, 3, 16, 9, 5, tzinfo=timezone.utc),
            raw_response={"data": {"id": "tweet-1"}},
            dry_run=False,
        )
        auth_service = Mock()
        auth_service.get_valid_user_access_token.return_value = "user-access-token"
        service = XPublicationService(
            session,
            publisher=publisher,
            auth_service=auth_service,
            scheduler=build_scheduler(current_time=now),
        )

        pending = service.list_pending(limit=10)
        result = service.publish_pending(limit=10, dry_run=False)
        session.commit()

        assert [row.id for row in pending] == [1]
        assert [row.id for row in result.rows] == [1]
        assert session.get(ContentCandidate, 8).external_publication_ref is None
    finally:
        session.close()
