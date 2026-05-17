from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus
from app.db.models import ContentCandidate
from app.schemas.editorial_day_plan import (
    EditorialDayPlanEntry,
    EditorialDayPlanReport,
    EditorialDayPlanScheduleSummary,
    EditorialDayPlanStatusSummary,
    EditorialDayPlanTypeItem,
)
from app.services.x_publication_scheduler import _WEEKDAY_TO_KEY, load_publication_schedule

_DEFAULT_ENTRY_LIMIT = 8
_DEFAULT_LOOKBACK_DAYS = 10
_STATUS_SORT_ORDER = {
    str(ContentCandidateStatus.APPROVED): 0,
    str(ContentCandidateStatus.DRAFT): 1,
    str(ContentCandidateStatus.PUBLISHED): 2,
    str(ContentCandidateStatus.REJECTED): 3,
}


class EditorialDayPlanService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        entry_limit: int = _DEFAULT_ENTRY_LIMIT,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.timezone = ZoneInfo(self.settings.timezone)
        self.entry_limit = entry_limit
        self.lookback_days = lookback_days
        self.schedule = load_publication_schedule()

    def build_report(self, target_date: date | None = None) -> EditorialDayPlanReport:
        selected_date = target_date or datetime.now(self.timezone).date()
        rows = self._load_candidate_rows(selected_date)
        filtered = [row for row in rows if self._matches_target_date(row, selected_date)]
        filtered.sort(key=self._sort_key)

        type_counter = Counter(row.content_type for row in filtered)
        status_summary = EditorialDayPlanStatusSummary(
            total_candidates=len(filtered),
            published_count=sum(1 for row in filtered if row.status == str(ContentCandidateStatus.PUBLISHED)),
            approved_count=sum(1 for row in filtered if row.status == str(ContentCandidateStatus.APPROVED)),
            draft_count=sum(1 for row in filtered if row.status == str(ContentCandidateStatus.DRAFT)),
            rejected_count=sum(1 for row in filtered if row.status == str(ContentCandidateStatus.REJECTED)),
            pending_count=sum(
                1
                for row in filtered
                if row.status in {str(ContentCandidateStatus.APPROVED), str(ContentCandidateStatus.DRAFT)}
            ),
        )

        by_type = [
            EditorialDayPlanTypeItem(content_type=content_type, count=count)
            for content_type, count in sorted(type_counter.items(), key=lambda item: (-item[1], item[0]))
        ]
        entries = [
            EditorialDayPlanEntry(
                id=row.id,
                status=row.status,
                content_type=row.content_type,
                competition=self._competition_label(row),
                priority=int(row.priority or 0),
            )
            for row in filtered[: self.entry_limit]
        ]

        return EditorialDayPlanReport(
            target_date=selected_date,
            timezone=self.settings.timezone,
            generated_at=datetime.now(self.timezone),
            schedule=self._schedule_summary(selected_date),
            status=status_summary,
            by_content_type=by_type,
            entries=entries,
        )

    def render_console(self, report: EditorialDayPlanReport) -> str:
        lines = [
            f"futbolbalear - plan editorial {report.target_date.isoformat()}",
            "",
            "Calendario",
            f"- dia: {report.schedule.day_key}",
        ]
        if report.schedule.publish_after:
            lines.append(f"- publicar desde: {report.schedule.publish_after}")
        if report.schedule.scheduled_types:
            lines.append(f"- tipos programados: {', '.join(report.schedule.scheduled_types)}")
        else:
            lines.append("- sin tipos programados por calendario")

        lines.extend(
            [
                "",
                "Estado actual",
                f"- total previstas: {report.status.total_candidates}",
                f"- ya publicadas: {report.status.published_count}",
                f"- pendientes: {report.status.pending_count}",
                f"- drafts: {report.status.draft_count}",
                f"- rechazadas: {report.status.rejected_count}",
            ]
        )

        if report.by_content_type:
            lines.extend(["", "Tipos"])
            lines.extend(f"- {item.content_type}: {item.count}" for item in report.by_content_type)

        lines.extend(["", "Piezas del dia"])
        if report.entries:
            lines.extend(
                f"- {entry.status} | {entry.content_type} | {entry.competition} | id={entry.id}"
                for entry in report.entries
            )
            remaining = report.status.total_candidates - len(report.entries)
            if remaining > 0:
                lines.append(f"- (+{remaining} pieza/s mas)")
        else:
            lines.append("- sin piezas previstas actualmente")

        lines.extend(["", f"Generado: {report.generated_at.strftime('%Y-%m-%d %H:%M')} ({report.timezone})"])
        return "\n".join(lines)

    def render_telegram(self, report: EditorialDayPlanReport) -> str:
        lines = [
            f"futbolbalear - agenda editorial {report.target_date.isoformat()}",
            "",
            "Calendario",
            f"- dia: {report.schedule.day_key}",
        ]
        if report.schedule.publish_after:
            lines.append(f"- publicar desde: {report.schedule.publish_after}")
        if report.schedule.scheduled_types:
            lines.append(f"- tipos: {', '.join(report.schedule.scheduled_types)}")

        lines.extend(
            [
                "",
                "Estado",
                f"- total previstas: {report.status.total_candidates}",
                f"- ya publicadas: {report.status.published_count}",
                f"- pendientes: {report.status.pending_count}",
                f"- rechazadas: {report.status.rejected_count}",
            ]
        )
        if report.by_content_type:
            lines.append("- por tipo: " + ", ".join(f"{item.content_type} ({item.count})" for item in report.by_content_type[:4]))

        lines.extend(["", "Piezas"])
        if report.entries:
            for entry in report.entries:
                lines.append(f"- {entry.status} | {entry.content_type} | {self._truncate(entry.competition, 40)}")
            remaining = report.status.total_candidates - len(report.entries)
            if remaining > 0:
                lines.append(f"- (+{remaining} pieza/s mas)")
        else:
            lines.append("- sin piezas previstas actualmente")

        return "\n".join(lines)

    def _load_candidate_rows(self, target_date: date) -> list[ContentCandidate]:
        window_start = datetime.combine(
            target_date - timedelta(days=max(self.lookback_days, 1) - 1),
            datetime.min.time(),
            tzinfo=self.timezone,
        ).astimezone(UTC)
        query = (
            select(ContentCandidate)
            .where(
                or_(
                    ContentCandidate.created_at >= window_start,
                    ContentCandidate.published_at >= window_start,
                    ContentCandidate.scheduled_at >= window_start,
                )
            )
            .order_by(ContentCandidate.created_at.asc(), ContentCandidate.id.asc())
        )
        return self.session.execute(query).scalars().all()

    def _matches_target_date(self, candidate: ContentCandidate, target_date: date) -> bool:
        reference_date = self._candidate_reference_date(candidate)
        if reference_date is not None:
            return reference_date == target_date
        for timestamp in (candidate.scheduled_at, candidate.published_at, candidate.created_at):
            if self._local_date(timestamp) == target_date:
                return True
        return False

    def _schedule_summary(self, target_date: date) -> EditorialDayPlanScheduleSummary:
        day_key = _WEEKDAY_TO_KEY[target_date.weekday()]
        day_schedule = self.schedule.day(day_key)
        if day_schedule is None:
            return EditorialDayPlanScheduleSummary(day_key=day_key)
        return EditorialDayPlanScheduleSummary(
            day_key=day_key,
            publish_after=day_schedule.publish_after.strftime("%H:%M"),
            scheduled_types=sorted(day_schedule.types),
        )

    def _candidate_reference_date(self, candidate: ContentCandidate) -> date | None:
        payload_json = candidate.payload_json or {}
        if not isinstance(payload_json, dict):
            return None
        value = payload_json.get("reference_date")
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _competition_label(self, candidate: ContentCandidate) -> str:
        payload_json = candidate.payload_json or {}
        if isinstance(payload_json, dict):
            competition_name = payload_json.get("competition_name")
            if isinstance(competition_name, str) and competition_name.strip():
                return competition_name.strip()
        return candidate.competition_slug

    def _local_date(self, value: datetime | None) -> date | None:
        if value is None:
            return None
        normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return normalized.astimezone(self.timezone).date()

    def _sort_key(self, candidate: ContentCandidate) -> tuple[int, int, datetime, int]:
        status_rank = _STATUS_SORT_ORDER.get(candidate.status, 99)
        priority = -int(candidate.priority or 0)
        created_at = candidate.created_at or datetime.min.replace(tzinfo=UTC)
        return (status_rank, priority, created_at, candidate.id)

    def _truncate(self, value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: max(limit - 3, 0)].rstrip() + "..."
