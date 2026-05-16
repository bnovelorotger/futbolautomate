from __future__ import annotations

import json
from dataclasses import dataclass
from collections.abc import Sequence

from sqlalchemy import delete, select

from app.db.models import MatchEvent
from app.db.repositories.base import BaseRepository


@dataclass(slots=True)
class MatchEventSyncResult:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: bool = False

    @property
    def changed(self) -> bool:
        return any((self.inserted, self.updated, self.deleted))


class MatchEventRepository(BaseRepository[MatchEvent]):
    def replace_for_match(self, match_id: int, payloads: Sequence[dict]) -> tuple[int, int]:
        existing = self.session.scalars(
            select(MatchEvent).where(MatchEvent.match_id == match_id)
        ).all()
        deleted = len(existing)
        self.session.execute(delete(MatchEvent).where(MatchEvent.match_id == match_id))

        inserted = 0
        for payload in payloads:
            self.session.add(MatchEvent(**payload))
            inserted += 1
        self.session.flush()
        return inserted, deleted

    def list_for_match(self, match_id: int) -> list[MatchEvent]:
        return self.session.scalars(
            select(MatchEvent)
            .where(MatchEvent.match_id == match_id)
            .order_by(MatchEvent.sort_order.asc(), MatchEvent.id.asc())
        ).all()

    def sync_for_match(self, match_id: int, payloads: Sequence[dict]) -> MatchEventSyncResult:
        normalized_payloads = self._dedupe_payloads(match_id, payloads)
        existing = self.list_for_match(match_id)

        if self._events_match(existing, normalized_payloads):
            return MatchEventSyncResult(unchanged=True)

        existing_by_key = {
            event.source_event_key: event
            for event in existing
        }
        incoming_keys = {payload["source_event_key"] for payload in normalized_payloads}
        result = MatchEventSyncResult()

        for payload in normalized_payloads:
            source_event_key = payload["source_event_key"]
            current = existing_by_key.get(source_event_key)
            if current is None:
                self.session.add(MatchEvent(**payload))
                result.inserted += 1
                continue
            if self._event_needs_update(current, payload):
                self._apply_payload(current, payload)
                result.updated += 1

        for event in existing:
            if event.source_event_key in incoming_keys:
                continue
            self.session.delete(event)
            result.deleted += 1

        if result.changed:
            self.session.flush()
        return result

    def _dedupe_payloads(self, match_id: int, payloads: Sequence[dict]) -> list[dict]:
        deduped: dict[str, dict] = {}
        for payload in payloads:
            normalized = dict(payload)
            normalized["match_id"] = match_id
            source_event_key = str(normalized["source_event_key"]).strip()
            if not source_event_key:
                raise ValueError(f"MatchEvent sin source_event_key valido para match_id={match_id}")
            normalized["source_event_key"] = source_event_key
            normalized["raw_payload"] = normalized.get("raw_payload") or {}
            deduped[source_event_key] = normalized
        ordered_payloads = list(deduped.values())
        for index, payload in enumerate(ordered_payloads, start=1):
            payload["sort_order"] = index
        return ordered_payloads

    def _events_match(self, existing: Sequence[MatchEvent], payloads: Sequence[dict]) -> bool:
        if len(existing) != len(payloads):
            return False
        return all(
            self._event_signature(event) == self._payload_signature(payload)
            for event, payload in zip(existing, payloads, strict=False)
        )

    def _event_needs_update(self, event: MatchEvent, payload: dict) -> bool:
        return self._event_signature(event) != self._payload_signature(payload)

    def _apply_payload(self, event: MatchEvent, payload: dict) -> None:
        for field in (
            "team_id",
            "team_side",
            "event_type",
            "period",
            "minute_raw",
            "minute",
            "minute_extra",
            "player_raw",
            "player_source_url",
            "sort_order",
            "source_event_key",
            "raw_payload",
        ):
            setattr(event, field, payload.get(field))

    def _event_signature(self, event: MatchEvent) -> tuple[object, ...]:
        return (
            event.team_id,
            event.team_side,
            event.event_type,
            event.period,
            event.minute_raw,
            event.minute,
            event.minute_extra,
            event.player_raw,
            event.player_source_url,
            event.sort_order,
            event.source_event_key,
            self._normalize_raw_payload(event.raw_payload),
        )

    def _payload_signature(self, payload: dict) -> tuple[object, ...]:
        return (
            payload.get("team_id"),
            payload.get("team_side"),
            payload.get("event_type"),
            payload.get("period"),
            payload.get("minute_raw"),
            payload.get("minute"),
            payload.get("minute_extra"),
            payload.get("player_raw"),
            payload.get("player_source_url"),
            payload.get("sort_order"),
            payload.get("source_event_key"),
            self._normalize_raw_payload(payload.get("raw_payload")),
        )

    def _normalize_raw_payload(self, raw_payload: dict | None) -> str:
        return json.dumps(raw_payload or {}, sort_keys=True, ensure_ascii=True)
