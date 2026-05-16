from __future__ import annotations

from sqlalchemy import select

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
