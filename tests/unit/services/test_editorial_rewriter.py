from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.exceptions import InvalidStateTransitionError
from app.core.enums import ContentType
from app.db.base import Base
from app.db.models import Competition, ContentCandidate
from app.llm.providers.base import LLMConfigurationError, LLMProviderError
from app.llm.schemas import EditorialRewriteLLMResponse
from app.services.editorial_rewriter import (
    EditorialRewriterService,
    is_candidate_eligible_for_rewrite,
)


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def build_settings(**overrides) -> Settings:
    payload = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "editorial_rewrite_provider": "openai",
        "editorial_rewrite_api_key": "openai-api-key",
        "editorial_rewrite_api_url": "https://api.openai.com/v1/responses",
        "editorial_rewrite_model": "gpt-4.1-mini",
        "editorial_rewrite_max_chars": 280,
    }
    payload.update(overrides)
    return Settings(**payload)


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
                text_draft="RESULTADO FINAL\n\nTorrent CF 1-0 UE Porreres\n\n2a RFEF Grupo 3\nJornada 26\nEstado: finished",
                payload_json={"source_payload": {"home_team": "Torrent CF", "away_team": "UE Porreres", "home_score": 1, "away_score": 0}},
                source_summary_hash="hash-1",
                scheduled_at=now,
                status="draft",
                rewritten_text=None,
                rewrite_status=None,
                rewrite_model=None,
                rewrite_timestamp=None,
                rewrite_error=None,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=2,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="preview",
                priority=90,
                text_draft="PREVIA",
                payload_json={},
                source_summary_hash="hash-2",
                scheduled_at=now,
                status="approved",
                rewritten_text="Texto ya reescrito",
                rewrite_status="rewritten",
                rewrite_model="gpt-4.1-mini",
                rewrite_timestamp=now,
                rewrite_error=None,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=3,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="ranking",
                priority=70,
                text_draft="   ",
                payload_json={},
                source_summary_hash="hash-3",
                scheduled_at=now,
                status="published",
                rewritten_text=None,
                rewrite_status=None,
                rewrite_model=None,
                rewrite_timestamp=None,
                rewrite_error=None,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                id=4,
                competition_slug="segunda_rfef_g3_baleares",
                content_type="standings",
                priority=60,
                text_draft="CLASIFICACION\n\n1. UE Sant Andreu - 54 pts",
                payload_json={},
                source_summary_hash="hash-4",
                scheduled_at=now,
                status="rejected",
                rewritten_text=None,
                rewrite_status=None,
                rewrite_model=None,
                rewrite_timestamp=None,
                rewrite_error=None,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()


def test_editorial_rewriter_eligibility_filter() -> None:
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
        assert is_candidate_eligible_for_rewrite(candidate_1) is True
        assert is_candidate_eligible_for_rewrite(candidate_2) is False
        assert is_candidate_eligible_for_rewrite(candidate_2, overwrite=True) is True
        assert is_candidate_eligible_for_rewrite(candidate_3) is False
        assert is_candidate_eligible_for_rewrite(candidate_4) is False
    finally:
        session.close()


def test_editorial_rewriter_dry_run_without_provider_config_stays_local() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        service = EditorialRewriterService(
            session,
            settings=build_settings(editorial_rewrite_api_key=None, editorial_rewrite_model=None),
        )

        result = service.rewrite_candidate(1, dry_run=True)

        assert result.dry_run is True
        assert result.candidate.rewrite_status == "dry_run_unconfigured"
        assert result.candidate.rewritten_text == result.candidate.text_draft
        assert session.get(ContentCandidate, 1).rewritten_text is None
    finally:
        session.close()


def test_editorial_rewriter_rewrites_successfully_with_provider() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        provider = Mock()
        provider.rewrite.return_value = EditorialRewriteLLMResponse(
            rewritten_text="Torrent CF se impuso por 1-0 a la UE Porreres en la jornada 26 de la 2a RFEF Grupo 3.",
            model="gpt-4.1-mini",
            rewritten_at=datetime(2026, 3, 15, 10, 5, tzinfo=timezone.utc),
            raw_response={},
        )
        service = EditorialRewriterService(session, provider=provider, settings=build_settings())

        result = service.rewrite_candidate(1, dry_run=False)
        session.commit()

        assert result.dry_run is False
        assert result.candidate.rewrite_status == "rewritten"
        assert "Torrent CF se impuso" in (result.candidate.rewritten_text or "")
        persisted = session.get(ContentCandidate, 1)
        assert persisted.rewritten_text == result.candidate.rewritten_text
        assert persisted.rewrite_model == "gpt-4.1-mini"
        assert persisted.rewrite_error is None
        provider.rewrite.assert_called_once()
    finally:
        session.close()


def test_editorial_rewriter_records_provider_error() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        provider = Mock()
        provider.rewrite.side_effect = LLMProviderError("timeout")
        service = EditorialRewriterService(session, provider=provider, settings=build_settings())

        with pytest.raises(LLMProviderError):
            service.rewrite_candidate(1, dry_run=False)
        session.commit()

        persisted = session.get(ContentCandidate, 1)
        assert persisted.rewrite_status == "failed"
        assert persisted.rewrite_error == "timeout"
        assert persisted.rewrite_timestamp is not None
    finally:
        session.close()


def test_editorial_rewriter_rejects_invalid_states_and_requires_overwrite() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        provider = Mock()
        service = EditorialRewriterService(session, provider=provider, settings=build_settings())

        with pytest.raises(InvalidStateTransitionError):
            service.rewrite_candidate(2, dry_run=False)

        with pytest.raises(InvalidStateTransitionError):
            service.rewrite_candidate(3, dry_run=False)

        with pytest.raises(InvalidStateTransitionError):
            service.rewrite_candidate(4, dry_run=False)
    finally:
        session.close()


def test_editorial_rewriter_supports_overwrite_and_batches() -> None:
    session = build_session()
    try:
        seed_candidates(session)
        provider = Mock()
        provider.rewrite.return_value = EditorialRewriteLLMResponse(
            rewritten_text="Previa reescrita limpia",
            model="gpt-4.1-mini",
            rewritten_at=datetime(2026, 3, 15, 10, 6, tzinfo=timezone.utc),
            raw_response={},
        )
        service = EditorialRewriterService(session, provider=provider, settings=build_settings())

        single = service.rewrite_candidate(2, dry_run=False, overwrite=True)
        batch = service.rewrite_pending(limit=5, dry_run=True, overwrite=True)

        assert single.overwritten is True
        assert single.candidate.rewritten_text == "Previa reescrita limpia"
        assert batch.dry_run is True
        assert batch.rewritten_count >= 2
    finally:
        session.close()
