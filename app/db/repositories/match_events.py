from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from app.db.models import Match, MatchEvent
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
    _UPSERT_FIELDS = (
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
        "raw_payload",
    )

    def goals_by_half_for_competition(
        self,
        competition_slug: str,
        season: str | None = None,
    ) -> dict[str, int]:
        """Return {"first_half": N, "second_half": N, "unknown_half": N}.

        Counts goal events split by minute: <= 45 is first half, > 45 is second
        half, and None is unknown_half. Only matches with has_scorers=True are
        included so partial-coverage matches don't skew the counts.
        """
        query = (
            select(MatchEvent.minute)
            .join(Match, Match.id == MatchEvent.match_id)
            .where(
                Match.competition.has(code=competition_slug),
                Match.has_scorers.is_(True),
                MatchEvent.event_type == "goal",
            )
        )
        if season is not None:
            query = query.where(Match.season == season)

        rows = self.session.execute(query).all()
        first_half = 0
        second_half = 0
        unknown_half = 0
        for (minute,) in rows:
            if minute is None:
                unknown_half += 1
            elif int(minute) <= 45:
                first_half += 1
            else:
                second_half += 1
        return {
            "first_half": first_half,
            "second_half": second_half,
            "unknown_half": unknown_half,
        }

    def top_scorers_for_competition(
        self,
        competition_slug: str,
        *,
        season: str | None = None,
        goal_event_types: tuple[str, ...] = ("goal",),
        limit: int = 10,
    ) -> list[tuple[str, int]]:
        """Return (player_name, goal_count) pairs sorted descending by goals.

        Only includes matches where has_scorers=True (closed scorer coverage).
        player_raw values are stripped and title-cased; blank names are excluded.
        """
        query = (
            select(
                MatchEvent.player_raw,
                func.count(MatchEvent.id).label("goal_count"),
            )
            .join(Match, Match.id == MatchEvent.match_id)
            .where(
                Match.competition.has(code=competition_slug),
                Match.has_scorers.is_(True),
                MatchEvent.event_type.in_(goal_event_types),
                MatchEvent.player_raw.is_not(None),
                func.trim(MatchEvent.player_raw) != "",
            )
            .group_by(MatchEvent.player_raw)
            .order_by(func.count(MatchEvent.id).desc(), MatchEvent.player_raw.asc())
            .limit(limit)
        )
        if season is not None:
            query = query.where(Match.season == season)
        rows = self.session.execute(query).all()
        return [
            (str(player_raw).strip().title(), goal_count) for player_raw, goal_count in rows if str(player_raw).strip()
        ]

    def replace_for_match(self, match_id: int, payloads: Sequence[dict]) -> tuple[int, int]:
        existing = self.session.scalars(select(MatchEvent).where(MatchEvent.match_id == match_id)).all()
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

        result = self._build_sync_result(existing, normalized_payloads)
        try:
            self._persist_sync(match_id, normalized_payloads)
        except IntegrityError as exc:
            if not self._is_match_source_key_violation(exc):
                raise
            current = self.list_for_match(match_id)
            if self._events_match(current, normalized_payloads):
                return result
            self._persist_sync(match_id, normalized_payloads)
        return result

    def _build_sync_result(
        self,
        existing: Sequence[MatchEvent],
        payloads: Sequence[dict],
    ) -> MatchEventSyncResult:
        existing_by_key = {event.source_event_key: event for event in existing}
        incoming_keys = {payload["source_event_key"] for payload in payloads}
        result = MatchEventSyncResult()

        for payload in payloads:
            source_event_key = payload["source_event_key"]
            current = existing_by_key.get(source_event_key)
            if current is None:
                result.inserted += 1
                continue
            if self._event_needs_update(current, payload):
                result.updated += 1

        for event in existing:
            if event.source_event_key in incoming_keys:
                continue
            result.deleted += 1
        return result

    def _persist_sync(self, match_id: int, payloads: Sequence[dict]) -> None:
        with self.session.begin_nested():
            self._acquire_match_lock(match_id)
            self._upsert_payloads(payloads)
            self._delete_missing_events(match_id, payloads)
            self.session.flush()

    def _acquire_match_lock(self, match_id: int) -> None:
        dialect_name = self.session.get_bind().dialect.name
        if dialect_name == "postgresql":
            # pg_advisory_xact_lock is re-entrant within the same session and
            # releases automatically when the enclosing transaction commits/rolls back.
            # Using match_id directly as the lock key (bigint space is fine for match PKs).
            self.session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": match_id})
        # SQLite is single-writer by design; no lock needed.

    def _upsert_payloads(self, payloads: Sequence[dict]) -> None:
        if not payloads:
            return
        statement = self._build_upsert_statement(payloads)
        self.session.execute(statement)

    def _build_upsert_statement(self, payloads: Sequence[dict]):
        dialect_name = self.session.get_bind().dialect.name
        if dialect_name == "postgresql":
            insert_statement = postgresql_insert(MatchEvent).values(payloads)
            return insert_statement.on_conflict_do_update(
                constraint="uq_match_events_match_source_key",
                set_={field: getattr(insert_statement.excluded, field) for field in self._UPSERT_FIELDS},
            )
        if dialect_name == "sqlite":
            insert_statement = sqlite_insert(MatchEvent).values(payloads)
            return insert_statement.on_conflict_do_update(
                index_elements=[MatchEvent.match_id, MatchEvent.source_event_key],
                set_={field: getattr(insert_statement.excluded, field) for field in self._UPSERT_FIELDS},
            )
        raise NotImplementedError(f"Dialecto no soportado para sync concurrente de match_events: {dialect_name}")

    def _delete_missing_events(self, match_id: int, payloads: Sequence[dict]) -> None:
        incoming_keys = {payload["source_event_key"] for payload in payloads}
        statement = delete(MatchEvent).where(MatchEvent.match_id == match_id)
        if incoming_keys:
            statement = statement.where(MatchEvent.source_event_key.not_in(incoming_keys))
        self.session.execute(statement)

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

    def _is_match_source_key_violation(self, exc: IntegrityError) -> bool:
        original = getattr(exc, "orig", None)
        message = str(original or exc)
        return (
            (getattr(original, "pgcode", None) == "23505" and "uq_match_events_match_source_key" in message)
            or ("UNIQUE constraint failed: match_events.match_id, match_events.source_event_key" in message)
            or (
                "duplicate key value violates unique constraint" in message
                and "uq_match_events_match_source_key" in message
            )
        )
