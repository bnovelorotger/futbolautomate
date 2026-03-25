from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import date, datetime
from pathlib import Path
import re

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.db.models import ContentCandidate
from app.schemas.export_json import ExportJsonBlockedSeries, ExportJsonEntry, ExportJsonResult
from app.services.editorial_candidate_window import EditorialCandidateWindowService
from app.services.editorial_quality_checks import EditorialQualityChecksService
from app.services.editorial_text_selector import EditorialTextSelectorService
from app.services.editorial_formatter import EditorialFormatterService

_PARTITION_SUFFIX_PATTERN = re.compile(r"\((\d+)/(\d+)\)\s*$")
_ROUND_TITLE_PATTERN = re.compile(r"\bJ\d+\b", re.IGNORECASE)


@dataclass(slots=True)
class _PartitionSeriesMember:
    candidate: ContentCandidate
    entry: ExportJsonEntry
    part_index: int
    part_total: int
    series_key: tuple[str, str, str, str]
    competition: str
    group: str
    round_label: str


class ExportJsonService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        output_path: Path | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.output_path = output_path or (self.settings.app_root / "export" / "legacy_export.json")
        self.selector = EditorialTextSelectorService(session)
        self.window = EditorialCandidateWindowService(session, settings=self.settings)
        self.quality = EditorialQualityChecksService(session, settings=self.settings)
        self.formatter = EditorialFormatterService(session, settings=self.settings)

    def generate_export_file(
        self,
        *,
        reference_date: date | None = None,
        dry_run: bool = False,
        prefer_rewrite: bool | None = None,
    ) -> ExportJsonResult:
        selected_date = reference_date or self.window._today()
        rewrite_preference = True if prefer_rewrite is None else prefer_rewrite
        candidates = self._published_candidates()
        filtered = [
            candidate
            for candidate in candidates
            if self.window.matches_release_window(candidate, reference_date=selected_date)
        ]
        quality_rows = self.quality.check_candidates(
            [candidate.id for candidate in filtered],
            dry_run=True,
            prefer_rewrite=rewrite_preference,
        ).rows if filtered else []
        passed_ids = {row.id for row in quality_rows if row.passed}

        blocked_series: list[ExportJsonBlockedSeries] = []
        entries_by_key: dict[tuple[str, str, str, date | None, str], ExportJsonEntry] = {}
        standalone_entries: list[tuple[ContentCandidate, ExportJsonEntry]] = []
        partitioned_groups: dict[tuple[str, str, str, str], list[_PartitionSeriesMember]] = {}
        for candidate in filtered:
            entry = self._entry(candidate, reference_date=selected_date, prefer_rewrite=rewrite_preference)
            partition_member = self._partition_series_member(candidate, entry)
            if partition_member is None:
                standalone_entries.append((candidate, entry))
                continue
            partitioned_groups.setdefault(partition_member.series_key, []).append(partition_member)

        for candidate, entry in standalone_entries:
            if candidate.id not in passed_ids:
                continue
            self._add_entry(entries_by_key, candidate, entry)

        for members in partitioned_groups.values():
            selected_members, blocked = self._resolve_partition_series(members, passed_ids=passed_ids)
            if blocked is not None:
                blocked_series.append(blocked)
                continue
            for member in selected_members:
                self._add_entry(entries_by_key, member.candidate, member.entry)

        rows = sorted(
            entries_by_key.values(),
            key=lambda row: (
                self._logical_day_index(row.content_type, row.match_date),
                row.competition,
                row.group,
                row.match_date or selected_date,
                row.id,
            ),
        )
        payload = [row.model_dump(mode="json") for row in rows]
        if not dry_run:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return ExportJsonResult(
            dry_run=dry_run,
            reference_date=selected_date,
            path=str(self.output_path),
            generated_count=len(rows),
            blocked_series_count=len(blocked_series),
            blocked_series=blocked_series,
            rows=rows,
        )

    def _published_candidates(self) -> list[ContentCandidate]:
        query = (
            select(ContentCandidate)
            .where(ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED))
            .order_by(
                case((ContentCandidate.published_at.is_(None), 1), else_=0),
                ContentCandidate.published_at.desc(),
                ContentCandidate.created_at.desc(),
                ContentCandidate.priority.desc(),
            )
        )
        return self.session.execute(query).scalars().all()

    def _entry(
        self,
        candidate: ContentCandidate,
        *,
        reference_date: date,
        prefer_rewrite: bool,
    ) -> ExportJsonEntry:
        selection = self.selector.select_text(candidate, prefer_rewrite=prefer_rewrite)
        payload_json = candidate.payload_json or {}
        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        competition_name = str(payload_json.get("competition_name") or self.formatter._competition_name(candidate.competition_slug))
        competition = self.formatter._competition_title(candidate.competition_slug, competition_name)
        group = self.formatter._group_title(candidate.competition_slug, competition_name, source_payload) or ""
        match_date = self.window.candidate_match_date(candidate, reference_date=reference_date)
        return ExportJsonEntry(
            id=candidate.id,
            content_type=str(ContentType(candidate.content_type)),
            competition=competition,
            group=group,
            match_date=match_date,
            tweet=selection.text,
            created_at=candidate.created_at or candidate.published_at or datetime.now(),
        )

    def _add_entry(
        self,
        entries_by_key: dict[tuple[str, str, str, date | None, str], ExportJsonEntry],
        candidate: ContentCandidate,
        entry: ExportJsonEntry,
    ) -> None:
        dedupe_key = (
            candidate.competition_slug,
            entry.content_type,
            entry.group,
            entry.match_date,
            entry.tweet,
        )
        current = entries_by_key.get(dedupe_key)
        if current is None or current.created_at < entry.created_at:
            entries_by_key[dedupe_key] = entry

    def _partition_series_member(
        self,
        candidate: ContentCandidate,
        entry: ExportJsonEntry,
    ) -> _PartitionSeriesMember | None:
        payload_json = candidate.payload_json or {}
        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        part_index = source_payload.get("part_index")
        part_total = source_payload.get("part_total")
        if not isinstance(part_index, int) or not isinstance(part_total, int) or part_total <= 1:
            title_match = _PARTITION_SUFFIX_PATTERN.search(self._entry_title(entry))
            if title_match is None:
                return None
            part_index = int(title_match.group(1))
            part_total = int(title_match.group(2))
        if part_total <= 1:
            return None

        competition_name = str(payload_json.get("competition_name") or self.formatter._competition_name(candidate.competition_slug))
        group = entry.group or self.formatter._group_title(candidate.competition_slug, competition_name, source_payload) or ""
        round_label = self.formatter._round_title(source_payload) or self._round_from_title(self._entry_title(entry))
        series_key = (
            candidate.competition_slug,
            entry.content_type,
            group,
            round_label,
        )
        return _PartitionSeriesMember(
            candidate=candidate,
            entry=entry,
            part_index=part_index,
            part_total=part_total,
            series_key=series_key,
            competition=entry.competition,
            group=group,
            round_label=round_label,
        )

    def _resolve_partition_series(
        self,
        members: list[_PartitionSeriesMember],
        *,
        passed_ids: set[int],
    ) -> tuple[list[_PartitionSeriesMember], ExportJsonBlockedSeries | None]:
        part_totals = {member.part_total for member in members}
        available_by_part: dict[int, _PartitionSeriesMember] = {}
        for member in members:
            current = available_by_part.get(member.part_index)
            if current is None or current.entry.created_at < member.entry.created_at:
                available_by_part[member.part_index] = member

        available_parts = sorted(available_by_part)
        expected_total = max(part_totals) if part_totals else 0
        expected_parts = list(range(1, expected_total + 1))
        passed_parts = sorted(
            part_index
            for part_index, member in available_by_part.items()
            if member.candidate.id in passed_ids
        )

        if len(part_totals) != 1:
            return [], self._blocked_series(
                next(iter(available_by_part.values())),
                expected_parts=expected_parts,
                available_parts=available_parts,
                passed_parts=passed_parts,
                reason="mixed_partition_totals",
            )

        if available_parts != expected_parts:
            return [], self._blocked_series(
                next(iter(available_by_part.values())),
                expected_parts=expected_parts,
                available_parts=available_parts,
                passed_parts=passed_parts,
                reason="partition_series_incomplete",
            )

        if passed_parts != expected_parts:
            return [], self._blocked_series(
                next(iter(available_by_part.values())),
                expected_parts=expected_parts,
                available_parts=available_parts,
                passed_parts=passed_parts,
                reason="partition_series_quality_failed",
            )

        selected_members = [available_by_part[index] for index in expected_parts]
        return selected_members, None

    def _blocked_series(
        self,
        member: _PartitionSeriesMember,
        *,
        expected_parts: list[int],
        available_parts: list[int],
        passed_parts: list[int],
        reason: str,
    ) -> ExportJsonBlockedSeries:
        return ExportJsonBlockedSeries(
            content_type=member.entry.content_type,
            competition=member.competition,
            group=member.group,
            round_label=member.round_label,
            expected_parts=expected_parts,
            available_parts=available_parts,
            passed_parts=passed_parts,
            partition_series_complete=False,
            blocked_reason=reason,
        )

    def _entry_title(self, entry: ExportJsonEntry) -> str:
        return entry.tweet.splitlines()[0].strip() if entry.tweet else ""

    def _round_from_title(self, title: str) -> str:
        match = _ROUND_TITLE_PATTERN.search(title)
        return match.group(0).upper() if match else ""

    def _logical_day_index(self, content_type: str, match_date: date | None) -> int:
        content_kind = ContentType(content_type)
        if content_kind in {
            ContentType.PREVIEW,
            ContentType.FEATURED_MATCH_PREVIEW,
            ContentType.FEATURED_MATCH_EVENT,
        }:
            return 2
        if content_kind in {
            ContentType.RANKING,
            ContentType.STANDINGS_EVENT,
            ContentType.FORM_RANKING,
            ContentType.FORM_EVENT,
            ContentType.STAT_NARRATIVE,
            ContentType.METRIC_NARRATIVE,
            ContentType.VIRAL_STORY,
        }:
            return 1
        if match_date is not None and match_date.weekday() == 6:
            return 3
        return 0


def generate_export_file(
    session: Session,
    *,
    reference_date: date | None = None,
    dry_run: bool = False,
    prefer_rewrite: bool | None = None,
    settings: Settings | None = None,
    output_path: Path | None = None,
) -> ExportJsonResult:
    return ExportJsonService(
        session,
        settings=settings,
        output_path=output_path,
    ).generate_export_file(
        reference_date=reference_date,
        dry_run=dry_run,
        prefer_rewrite=prefer_rewrite,
    )
