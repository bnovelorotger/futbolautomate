from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.draft_temp import load_draft_temp_snapshot, store_draft_temp_snapshot
from app.db.base import Base
from app.db.models import Competition, ContentCandidate
from app.services.draft_temp_service import DraftTempService


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def seed_candidates(session: Session) -> None:
    now = datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc)
    competition = Competition(
        code="tercera_rfef_g11",
        name="3a RFEF Grupo 11",
        normalized_name="3a rfef grupo 11",
        category_level=5,
        gender="male",
        region="Baleares",
        country="Spain",
        federation="RFEF",
        source_name="futbolme",
        source_competition_id="3065",
    )
    session.add(competition)
    session.flush()
    session.add_all(
        [
            ContentCandidate(
                competition_slug="tercera_rfef_g11",
                content_type="results_roundup",
                priority=99,
                text_draft="draft text one",
                rewritten_text="rewrite text one",
                payload_json={"content_key": "results:1"},
                source_summary_hash="hash-1",
                status="draft",
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                competition_slug="tercera_rfef_g11",
                content_type="standings_roundup",
                priority=82,
                text_draft="draft text two",
                formatted_text="formatted text two",
                payload_json={"content_key": "standings:1"},
                source_summary_hash="hash-2",
                status="approved",
                scheduled_at=now,
                approved_at=now,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                competition_slug="tercera_rfef_g11",
                content_type="preview",
                priority=80,
                text_draft="draft text three",
                payload_json={"content_key": "preview:1"},
                source_summary_hash="hash-3",
                status="published",
                published_at=now,
                external_publication_ref="draft_123",
                external_channel="legacy_export",
                external_exported_at=now,
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                competition_slug="tercera_rfef_g11",
                content_type="ranking",
                priority=70,
                text_draft="draft text four",
                payload_json={"content_key": "ranking:1"},
                source_summary_hash="hash-4",
                status="published",
                published_at=now,
                external_publication_error="capacity_deferred:MONETIZATION_ERROR",
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                competition_slug="tercera_rfef_g11",
                content_type="match_result",
                priority=60,
                text_draft="draft text five",
                payload_json={"content_key": "match:1"},
                source_summary_hash="hash-5",
                status="published",
                published_at=now,
                external_publication_error="Export timeout",
                created_at=now,
                updated_at=now,
            ),
            ContentCandidate(
                competition_slug="tercera_rfef_g11",
                content_type="featured_match_event",
                priority=50,
                text_draft="draft text six",
                payload_json={"content_key": "featured:1"},
                source_summary_hash="hash-6",
                status="rejected",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()


def test_draft_temp_service_builds_snapshot_and_persists_json(tmp_path) -> None:
    session = build_session()
    try:
        seed_candidates(session)
        service = DraftTempService(session)

        snapshot = service.build_snapshot()
        path = store_draft_temp_snapshot(snapshot, path=tmp_path / "draft_temp.json")
        loaded = load_draft_temp_snapshot(path)

        assert snapshot.summary.total_candidates == 6
        assert snapshot.summary.active_candidates == 5
        assert snapshot.summary.included_rows == 5
        assert snapshot.summary.draft_count == 1
        assert snapshot.summary.approved_count == 1
        assert snapshot.summary.published_count == 3
        assert snapshot.summary.rejected_count == 1
        assert snapshot.summary.scheduled_pending_count == 1
        assert snapshot.summary.pending_export_count == 2
        assert snapshot.summary.exported_count == 1
        assert snapshot.summary.failed_export_count == 1
        assert snapshot.summary.capacity_deferred_count == 1

        assert [row.status for row in snapshot.rows] == [
            "draft",
            "approved",
            "published",
            "published",
            "published",
        ]
        assert snapshot.rows[0].selected_text_source == "rewritten_text"
        assert snapshot.rows[0].selected_text == "rewrite text one"
        assert snapshot.rows[1].selected_text_source == "formatted_text"
        assert snapshot.rows[1].selected_text == "formatted text two"
        assert snapshot.rows[2].selected_text_source == "text_draft"

        assert path.exists()
        assert loaded is not None
        assert loaded.summary.pending_export_count == 2

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["summary"]["capacity_deferred_count"] == 1
        assert len(payload["rows"]) == 5
    finally:
        session.close()
