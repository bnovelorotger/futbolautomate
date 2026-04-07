from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.schemas.export_base import ExportBaseDocument, ExportBaseItem, ExportBaseResult
from app.services.editorial_candidate_window import EditorialCandidateWindowService
from app.services.editorial_text_selector import EditorialTextSelectorService
from app.services.standings_card_service import generate_standings_card
from app.utils.time import utcnow

_SNAPSHOT_SCOPE = "weekly_snapshot"
_PREVIEW_TYPES = {
    ContentType.PREVIEW,
    ContentType.FEATURED_MATCH_PREVIEW,
    ContentType.FEATURED_MATCH_EVENT,
}
_POST_MATCHDAY_TYPES = {
    ContentType.RESULTS_ROUNDUP,
    ContentType.MATCH_RESULT,
    ContentType.STANDINGS,
    ContentType.STANDINGS_ROUNDUP,
    ContentType.STANDINGS_EVENT,
}
_WEEKLY_TYPES = {
    ContentType.RANKING,
    ContentType.METRIC_NARRATIVE,
    ContentType.STAT_NARRATIVE,
    ContentType.VIRAL_STORY,
    ContentType.FORM_EVENT,
    ContentType.FORM_RANKING,
}


def _usable_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = text.strip()
    return normalized or None


class ExportBaseService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        output_path: Path | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.output_path = output_path or (self.settings.app_root / "exports" / "export_base.json")
        self.window = EditorialCandidateWindowService(session, settings=self.settings)
        self.selector = EditorialTextSelectorService(session, settings=self.settings)

    def generate_export_file(
        self,
        *,
        reference_date: date | None = None,
        dry_run: bool = False,
    ) -> ExportBaseResult:
        target_date = reference_date or datetime.now(ZoneInfo(self.settings.timezone)).date()
        window_start, window_end = self._weekly_window(target_date)
        rows = self._candidates_for_snapshot()
        competitions: dict[str, dict[str, list[ExportBaseItem]]] = {}
        selected_topic_keys: set[tuple[str, str, str]] = set()

        for row in rows:
            if not self._included_in_snapshot(
                row,
                target_date=target_date,
                window_start=window_start,
                window_end=window_end,
            ):
                continue
            topic_key = self._topic_key(row)
            if topic_key in selected_topic_keys:
                continue
            selected_topic_keys.add(topic_key)

            text, source = self._selected_text(row)
            image_path: str | None = None
            if not dry_run and row.content_type == str(ContentType.STANDINGS_ROUNDUP):
                try:
                    image_path = generate_standings_card(
                        row,
                        output_root=self.output_path.parent,
                        output_date=target_date,
                    )
                except Exception:
                    image_path = None
            item = ExportBaseItem(
                id=row.id,
                text=text,
                selected_text_source=source,
                competition_slug=row.competition_slug,
                content_type=row.content_type,
                image_path=image_path,
                priority=row.priority,
                created_at=row.created_at or row.updated_at or utcnow(),
            )
            competition_bucket = competitions.setdefault(row.competition_slug, {})
            content_bucket = competition_bucket.setdefault(row.content_type, [])
            content_bucket.append(item)

        generated_at = utcnow()
        document = ExportBaseDocument(
            scope=_SNAPSHOT_SCOPE,
            target_date=target_date,
            window_start=window_start,
            window_end=window_end,
            generated_at=generated_at,
            total_items=sum(len(items) for group in competitions.values() for items in group.values()),
            competitions=competitions,
        )
        if not dry_run:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_text(
                json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return ExportBaseResult(
            scope=_SNAPSHOT_SCOPE,
            target_date=target_date,
            window_start=window_start,
            window_end=window_end,
            path=str(self.output_path),
            total_items=document.total_items,
            generated_at=generated_at,
            document=document,
        )

    def _candidates_for_snapshot(self) -> list[ContentCandidate]:
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.published_at.is_not(None),
            )
            .order_by(
                ContentCandidate.competition_slug.asc(),
                ContentCandidate.content_type.asc(),
                ContentCandidate.priority.desc(),
                ContentCandidate.published_at.desc().nullslast(),
                ContentCandidate.created_at.desc(),
                ContentCandidate.id.desc(),
            )
        )
        return self.session.execute(query).scalars().all()

    def _included_in_snapshot(
        self,
        candidate: ContentCandidate,
        *,
        target_date: date,
        window_start: date,
        window_end: date,
    ) -> bool:
        try:
            content_type = ContentType(candidate.content_type)
        except ValueError:
            return False
        if content_type in _PREVIEW_TYPES:
            return self._matches_preview_window(
                candidate,
                target_date=target_date,
                window_start=window_start,
                window_end=window_end,
            )
        if content_type in _POST_MATCHDAY_TYPES:
            return self._matches_post_window(
                candidate,
                target_date=target_date,
                window_start=window_start,
                window_end=window_end,
            )
        if content_type in _WEEKLY_TYPES:
            return self._matches_weekly_window(candidate, window_start=window_start, window_end=window_end)
        return self._matches_weekly_window(candidate, window_start=window_start, window_end=window_end)

    def _matches_preview_window(
        self,
        candidate: ContentCandidate,
        *,
        target_date: date,
        window_start: date,
        window_end: date,
    ) -> bool:
        preview_window_end = window_end
        if candidate.content_type == str(ContentType.PREVIEW):
            preview_window_end = self._effective_preview_window_end(target_date)
        context = self.window.competition_window(candidate.competition_slug, reference_date=target_date)
        candidate_round = self.window._candidate_round(candidate)
        match_dates = self.window._candidate_match_dates(candidate)
        if match_dates:
            earliest_date = min(match_dates)
            if earliest_date < target_date or earliest_date > preview_window_end:
                return False
            if context.next_match_date is not None and earliest_date == context.next_match_date:
                return True
        if candidate_round and context.next_round and candidate_round == context.next_round:
            return True
        return self._matches_date_window(
            candidate,
            start_date=target_date,
            end_date=preview_window_end,
        )

    def _matches_post_window(
        self,
        candidate: ContentCandidate,
        *,
        target_date: date,
        window_start: date,
        window_end: date,
    ) -> bool:
        context = self.window.competition_window(candidate.competition_slug, reference_date=target_date)
        candidate_round = self.window._candidate_round(candidate)
        match_dates = self.window._candidate_match_dates(candidate)
        if match_dates:
            latest_date = max(match_dates)
            if latest_date >= target_date:
                return False
            if context.current_match_date is not None and latest_date == context.current_match_date:
                return True
        if candidate_round and context.current_round and candidate_round == context.current_round:
            return True
        return self._matches_weekly_window(candidate, window_start=window_start, window_end=window_end)

    def _matches_weekly_window(
        self,
        candidate: ContentCandidate,
        *,
        window_start: date,
        window_end: date,
    ) -> bool:
        return self._matches_date_window(candidate, start_date=window_start, end_date=window_end)

    def _matches_date_window(
        self,
        candidate: ContentCandidate,
        *,
        start_date: date,
        end_date: date,
    ) -> bool:
        editorial_dates = self._editorial_dates(candidate)
        return any(start_date <= value <= end_date for value in editorial_dates)

    def _editorial_dates(self, candidate: ContentCandidate) -> list[date]:
        values: list[date] = []
        reference_date = self.window._candidate_reference_date(candidate)
        if reference_date is not None:
            values.append(reference_date)
        values.extend(self.window._candidate_match_dates(candidate))
        if not values:
            values.append(self.window._candidate_local_date(candidate))
        return sorted(set(values))

    def _selected_text(self, candidate: ContentCandidate) -> tuple[str, str]:
        try:
            content_type = ContentType(candidate.content_type)
        except ValueError:
            content_type = None

        if content_type in {ContentType.PREVIEW, ContentType.FEATURED_MATCH_PREVIEW}:
            try:
                selection = self.selector.select_text(candidate, prefer_rewrite=True)
                return selection.text, selection.source
            except InvalidStateTransitionError:
                pass

        rewrite_text = _usable_text(candidate.rewritten_text)
        if rewrite_text is not None:
            return candidate.rewritten_text or "", "rewritten_text"
        formatted_text = _usable_text(candidate.formatted_text)
        if formatted_text is not None:
            return candidate.formatted_text or "", "formatted_text"
        draft_text = _usable_text(candidate.text_draft)
        if draft_text is not None:
            return candidate.text_draft, "text_draft"
        if candidate.formatted_text is not None:
            return candidate.formatted_text, "formatted_text"
        return candidate.text_draft, "text_draft"

    def _topic_key(self, candidate: ContentCandidate) -> tuple[str, str, str]:
        payload_json = candidate.payload_json or {}
        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        standings_topic_key = self._standings_roundup_topic_key(candidate, source_payload)
        if standings_topic_key is not None:
            return (candidate.competition_slug, candidate.content_type, standings_topic_key)
        content_key = str(payload_json.get("content_key") or "").strip()
        if content_key:
            return (candidate.competition_slug, candidate.content_type, content_key)
        marker = {
            "reference_date": payload_json.get("reference_date"),
            "part_index": source_payload.get("part_index"),
            "part_total": source_payload.get("part_total"),
            "round_name": source_payload.get("round_name"),
            "group_label": source_payload.get("group_label"),
            "split_focus": source_payload.get("split_focus"),
            "story_type": source_payload.get("story_type"),
            "event_type": source_payload.get("event_type"),
            "team": source_payload.get("team"),
            "teams": source_payload.get("teams"),
            "featured_match": self._compact_match(source_payload.get("featured_match")),
            "matches": [self._compact_match(match) for match in (source_payload.get("matches") or []) if isinstance(match, dict)],
        }
        return (
            candidate.competition_slug,
            candidate.content_type,
            json.dumps(marker, ensure_ascii=False, sort_keys=True),
        )

    def _standings_roundup_topic_key(
        self,
        candidate: ContentCandidate,
        source_payload: dict[str, Any],
    ) -> str | None:
        if candidate.content_type != str(ContentType.STANDINGS_ROUNDUP):
            return None
        round_name = source_payload.get("round_name")
        group_label = source_payload.get("group_label")
        part_index = source_payload.get("part_index")
        part_total = source_payload.get("part_total")
        if round_name in (None, "") and group_label in (None, "") and part_index is None and part_total is None:
            return None
        return json.dumps(
            {
                "round_name": round_name,
                "group_label": group_label,
                "part_index": part_index,
                "part_total": part_total,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def _compact_match(self, match: Any) -> dict[str, Any] | None:
        if not isinstance(match, dict):
            return None
        return {
            "round_name": match.get("round_name"),
            "match_date": match.get("match_date"),
            "home_team": match.get("home_team"),
            "away_team": match.get("away_team"),
        }

    def _weekly_window(self, target_date: date) -> tuple[date, date]:
        window_start = target_date - timedelta(days=target_date.weekday())
        window_end = window_start + timedelta(days=6)
        return window_start, window_end

    def _effective_preview_window_end(self, target_date: date) -> date:
        days_ahead = 7
        if target_date.weekday() == 3:
            days_ahead = 10
        elif target_date.weekday() == 4:
            days_ahead = 9
        return target_date + timedelta(days=days_ahead)
