from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import MatchEvent
from app.db.repositories.match_events import MatchEventRepository
from tests.unit.services.test_editorial_narratives import build_session
from tests.unit.services.test_match_event_enricher import _seed_finished_match


def test_match_event_repository_sync_is_idempotent_for_unchanged_payloads() -> None:
    session = build_session()
    try:
        match = _seed_finished_match(session)
        repository = MatchEventRepository(session)
        payloads = [
            {
                "match_id": match.id,
                "team_id": match.home_team_id,
                "team_side": "home",
                "event_type": "goal",
                "period": "Primer Tiempo",
                "minute_raw": "38",
                "minute": 38,
                "minute_extra": None,
                "player_raw": "Jaume",
                "player_source_url": "https://example.com/player/jaume",
                "sort_order": 1,
                "source_event_key": "home-38-jaume",
                "raw_payload": {"source": "fixture"},
            }
        ]

        first = repository.sync_for_match(match.id, payloads)
        session.commit()
        first_ids = [
            event.id
            for event in session.execute(
                select(MatchEvent).where(MatchEvent.match_id == match.id).order_by(MatchEvent.sort_order.asc())
            ).scalars().all()
        ]

        second = repository.sync_for_match(match.id, payloads)
        session.commit()
        second_ids = [
            event.id
            for event in session.execute(
                select(MatchEvent).where(MatchEvent.match_id == match.id).order_by(MatchEvent.sort_order.asc())
            ).scalars().all()
        ]

        assert first.inserted == 1
        assert first.updated == 0
        assert first.deleted == 0
        assert second.unchanged is True
        assert second.changed is False
        assert second_ids == first_ids
    finally:
        session.close()


def test_match_event_repository_sync_dedupes_duplicate_source_event_keys() -> None:
    session = build_session()
    try:
        match = _seed_finished_match(session)
        repository = MatchEventRepository(session)

        repository.sync_for_match(
            match.id,
            [
                {
                    "match_id": match.id,
                    "team_id": match.home_team_id,
                    "team_side": "home",
                    "event_type": "goal",
                    "period": "Primer Tiempo",
                    "minute_raw": "12",
                    "minute": 12,
                    "minute_extra": None,
                    "player_raw": "Primero",
                    "player_source_url": None,
                    "sort_order": 1,
                    "source_event_key": "duplicated-key",
                    "raw_payload": {"source": "fixture", "slot": 1},
                },
                {
                    "match_id": match.id,
                    "team_id": match.home_team_id,
                    "team_side": "home",
                    "event_type": "goal",
                    "period": "Primer Tiempo",
                    "minute_raw": "12",
                    "minute": 12,
                    "minute_extra": None,
                    "player_raw": "Definitivo",
                    "player_source_url": None,
                    "sort_order": 2,
                    "source_event_key": "duplicated-key",
                    "raw_payload": {"source": "fixture", "slot": 2},
                },
                {
                    "match_id": match.id,
                    "team_id": match.away_team_id,
                    "team_side": "away",
                    "event_type": "goal",
                    "period": "Segundo Tiempo",
                    "minute_raw": "80",
                    "minute": 80,
                    "minute_extra": None,
                    "player_raw": "Rival",
                    "player_source_url": None,
                    "sort_order": 3,
                    "source_event_key": "away-80-rival",
                    "raw_payload": {"source": "fixture", "slot": 3},
                },
            ],
        )
        session.commit()

        events = session.execute(
            select(MatchEvent).where(MatchEvent.match_id == match.id).order_by(MatchEvent.sort_order.asc())
        ).scalars().all()

        assert len(events) == 2
        assert [event.sort_order for event in events] == [1, 2]
        assert events[0].player_raw == "Definitivo"
        assert events[0].source_event_key == "duplicated-key"
        assert events[1].source_event_key == "away-80-rival"
    finally:
        session.close()


def test_match_event_repository_sync_updates_existing_event_via_upsert() -> None:
    session = build_session()
    try:
        match = _seed_finished_match(session)
        repository = MatchEventRepository(session)
        initial_payload = {
            "match_id": match.id,
            "team_id": match.home_team_id,
            "team_side": "home",
            "event_type": "goal",
            "period": "Primer Tiempo",
            "minute_raw": "12",
            "minute": 12,
            "minute_extra": None,
            "player_raw": "Primero",
            "player_source_url": None,
            "sort_order": 1,
            "source_event_key": "home-12-player",
            "raw_payload": {"source": "fixture", "slot": 1},
        }
        updated_payload = {
            **initial_payload,
            "player_raw": "Definitivo",
            "raw_payload": {"source": "fixture", "slot": 2},
        }

        repository.sync_for_match(match.id, [initial_payload])
        session.commit()

        result = repository.sync_for_match(match.id, [updated_payload])
        session.commit()
        events = session.execute(
            select(MatchEvent).where(MatchEvent.match_id == match.id).order_by(MatchEvent.sort_order.asc())
        ).scalars().all()

        assert result.inserted == 0
        assert result.updated == 1
        assert result.deleted == 0
        assert len(events) == 1
        assert events[0].player_raw == "Definitivo"
        assert events[0].raw_payload == {"source": "fixture", "slot": 2}
    finally:
        session.close()


def test_match_event_repository_sync_retries_after_unique_violation(monkeypatch) -> None:
    session = build_session()
    try:
        match = _seed_finished_match(session)
        repository = MatchEventRepository(session)
        payloads = [
            {
                "match_id": match.id,
                "team_id": match.home_team_id,
                "team_side": "home",
                "event_type": "goal",
                "period": "Primer Tiempo",
                "minute_raw": "38",
                "minute": 38,
                "minute_extra": None,
                "player_raw": "Jaume",
                "player_source_url": "https://example.com/player/jaume",
                "sort_order": 1,
                "source_event_key": "home-38-jaume",
                "raw_payload": {"source": "fixture"},
            }
        ]
        original_persist = repository._persist_sync
        attempts = {"count": 0}

        class _FakePgUniqueViolation:
            pgcode = "23505"

            def __str__(self) -> str:
                return 'duplicate key value violates unique constraint "uq_match_events_match_source_key"'

        def _flaky_persist(match_id: int, current_payloads: list[dict]) -> None:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise IntegrityError("INSERT INTO match_events ...", None, _FakePgUniqueViolation())
            original_persist(match_id, current_payloads)

        monkeypatch.setattr(repository, "_persist_sync", _flaky_persist)

        result = repository.sync_for_match(match.id, payloads)
        session.commit()
        events = session.execute(
            select(MatchEvent).where(MatchEvent.match_id == match.id).order_by(MatchEvent.sort_order.asc())
        ).scalars().all()

        assert attempts["count"] == 2
        assert result.inserted == 1
        assert result.updated == 0
        assert result.deleted == 0
        assert len(events) == 1
        assert events[0].source_event_key == "home-38-jaume"
    finally:
        session.close()


def test_match_event_repository_sync_updates_existing_rows_and_deletes_missing_ones() -> None:
    session = build_session()
    try:
        match = _seed_finished_match(session)
        repository = MatchEventRepository(session)

        repository.sync_for_match(
            match.id,
            [
                {
                    "match_id": match.id,
                    "team_id": match.home_team_id,
                    "team_side": "home",
                    "event_type": "goal",
                    "period": "Primer Tiempo",
                    "minute_raw": "12",
                    "minute": 12,
                    "minute_extra": None,
                    "player_raw": "Primero",
                    "player_source_url": None,
                    "sort_order": 1,
                    "source_event_key": "home-12-primero",
                    "raw_payload": {"source": "fixture", "slot": 1},
                },
                {
                    "match_id": match.id,
                    "team_id": match.away_team_id,
                    "team_side": "away",
                    "event_type": "goal",
                    "period": "Segundo Tiempo",
                    "minute_raw": "80",
                    "minute": 80,
                    "minute_extra": None,
                    "player_raw": "Rival",
                    "player_source_url": None,
                    "sort_order": 2,
                    "source_event_key": "away-80-rival",
                    "raw_payload": {"source": "fixture", "slot": 2},
                },
            ],
        )
        session.commit()

        result = repository.sync_for_match(
            match.id,
            [
                {
                    "match_id": match.id,
                    "team_id": match.home_team_id,
                    "team_side": "home",
                    "event_type": "goal",
                    "period": "Primer Tiempo",
                    "minute_raw": "12",
                    "minute": 12,
                    "minute_extra": None,
                    "player_raw": "Actualizado",
                    "player_source_url": "https://example.com/player/actualizado",
                    "sort_order": 1,
                    "source_event_key": "home-12-primero",
                    "raw_payload": {"source": "fixture", "slot": 10},
                },
                {
                    "match_id": match.id,
                    "team_id": match.home_team_id,
                    "team_side": "home",
                    "event_type": "goal",
                    "period": "Segundo Tiempo",
                    "minute_raw": "75",
                    "minute": 75,
                    "minute_extra": None,
                    "player_raw": "Nuevo",
                    "player_source_url": None,
                    "sort_order": 2,
                    "source_event_key": "home-75-nuevo",
                    "raw_payload": {"source": "fixture", "slot": 20},
                },
            ],
        )
        session.commit()

        events = session.execute(
            select(MatchEvent).where(MatchEvent.match_id == match.id).order_by(MatchEvent.sort_order.asc())
        ).scalars().all()

        assert result.inserted == 1
        assert result.updated == 1
        assert result.deleted == 1
        assert len(events) == 2
        assert [event.source_event_key for event in events] == ["home-12-primero", "home-75-nuevo"]
        assert events[0].player_raw == "Actualizado"
        assert events[0].player_source_url == "https://example.com/player/actualizado"
        assert events[1].player_raw == "Nuevo"
    finally:
        session.close()


def test_acquire_match_lock_called_for_postgresql() -> None:
    """_acquire_match_lock executes pg_advisory_xact_lock for postgresql dialect."""
    mock_session = MagicMock()
    mock_session.get_bind.return_value.dialect.name = "postgresql"

    repo = MatchEventRepository(mock_session)
    repo._acquire_match_lock(42)

    mock_session.execute.assert_called_once()
    positional, keyword = mock_session.execute.call_args
    sql_text = str(positional[0])
    assert "pg_advisory_xact_lock" in sql_text
    assert positional[1] == {"id": 42}


def test_acquire_match_lock_skipped_for_sqlite() -> None:
    """_acquire_match_lock does nothing for sqlite dialect."""
    mock_session = MagicMock()
    mock_session.get_bind.return_value.dialect.name = "sqlite"

    repo = MatchEventRepository(mock_session)
    repo._acquire_match_lock(99)

    mock_session.execute.assert_not_called()
