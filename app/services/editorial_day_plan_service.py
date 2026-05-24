from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
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
from app.services.editorial_approval_policy import EditorialApprovalPolicyService
from app.services.editorial_ops import EditorialOperationsService
from app.services.editorial_phase import EditorialPhaseService
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
        self.editorial_ops = EditorialOperationsService(session)
        self.phase_service = EditorialPhaseService(session, settings=self.settings)
        self.approval_policy = EditorialApprovalPolicyService(session, settings=self.settings)

    def build_report(self, target_date: date | None = None) -> EditorialDayPlanReport:
        selected_date = target_date or datetime.now(self.timezone).date()
        scheduled_types = set(self._scheduled_content_types(selected_date))
        preview_report = self.editorial_ops.preview_day(selected_date)
        filtered_rows = [
            row for row in preview_report.rows if row.target_content_type.value in scheduled_types
        ]
        published_count = self._published_reference_day_count(selected_date, scheduled_types=scheduled_types)
        approval_result = self.approval_policy.autoapprove(
            reference_date=selected_date,
            limit=500,
            dry_run=True,
        )
        publishable_rows = [
            row
            for row in approval_result.rows
            if row.content_type.value in scheduled_types and row.autoapprovable
        ]
        manual_rows = [
            row
            for row in approval_result.rows
            if row.content_type.value in scheduled_types and not row.autoapprovable
        ]
        planned_rows = publishable_rows[: self._slot_publish_limit(selected_date)]
        type_counter = Counter(row.content_type.value for row in planned_rows)
        expected_total = sum(int(row.expected_count) for row in filtered_rows)
        blocked_tasks = sum(int(bool(row.missing_dependencies)) for row in filtered_rows)
        status_summary = EditorialDayPlanStatusSummary(
            total_candidates=expected_total,
            published_count=published_count,
            approved_count=len(publishable_rows),
            draft_count=len(manual_rows),
            rejected_count=blocked_tasks,
            pending_count=len(planned_rows),
        )

        by_type = [
            EditorialDayPlanTypeItem(content_type=content_type, count=count)
            for content_type, count in sorted(type_counter.items(), key=lambda item: (-item[1], item[0]))
        ]
        entries = [
            EditorialDayPlanEntry(
                id=row.id,
                status="auto",
                content_type=row.content_type.value,
                competition=self._competition_label_for_candidate(row.id, fallback=row.competition_slug),
                priority=int(row.priority or 0),
            )
            for row in planned_rows[: self.entry_limit]
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
            f"- fase: {report.schedule.editorial_phase or '-'}",
        ]
        if report.schedule.publish_slots:
            lines.append(f"- slots X: {', '.join(report.schedule.publish_slots)}")
        elif report.schedule.publish_after:
            lines.append(f"- publicar desde: {report.schedule.publish_after}")
        if report.schedule.scheduled_types:
            lines.append(f"- tipos programados: {', '.join(report.schedule.scheduled_types)}")
        else:
            lines.append("- sin tipos programados por calendario")

        lines.extend(
            [
                "",
                "Estado actual",
                f"- publicadas de la jornada: {report.status.published_count}",
                f"- publicables hoy: {report.status.approved_count}",
                f"- salida prevista en este slot: {report.status.pending_count}",
                f"- pendientes manuales hoy: {report.status.draft_count}",
                f"- tareas bloqueadas por planner: {report.status.rejected_count}",
                f"- carga total del planner: {report.status.total_candidates}",
            ]
        )

        if report.by_content_type:
            lines.extend(["", "Tipos"])
            lines.extend(f"- {item.content_type}: {item.count}" for item in report.by_content_type)

        lines.extend(["", "Piezas del dia"])
        if report.entries:
            lines.extend(
                f"- {entry.status} | {entry.content_type} | {entry.competition}"
                for entry in report.entries
            )
            remaining = max(report.status.pending_count - len(report.entries), 0)
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
            f"- fase: {report.schedule.editorial_phase or '-'}",
        ]
        if report.schedule.publish_slots:
            lines.append(f"- slots X: {', '.join(report.schedule.publish_slots)}")
        elif report.schedule.publish_after:
            lines.append(f"- publicar desde: {report.schedule.publish_after}")
        if report.schedule.scheduled_types:
            lines.append(f"- tipos: {', '.join(report.schedule.scheduled_types)}")

        lines.extend(
            [
                "",
                "Estado",
                f"- publicadas de la jornada: {report.status.published_count}",
                f"- publicables hoy: {report.status.approved_count}",
                f"- salida prevista en este slot: {report.status.pending_count}",
                f"- pendientes manuales hoy: {report.status.draft_count}",
                f"- tareas bloqueadas por planner: {report.status.rejected_count}",
            ]
        )
        if report.by_content_type:
            lines.append(
                "- por tipo: " + ", ".join(f"{item.content_type} ({item.count})" for item in report.by_content_type[:4])
            )

        lines.extend(["", "Piezas"])
        if report.entries:
            for entry in report.entries:
                lines.append(f"- {entry.status} | {entry.content_type} | {self._truncate(entry.competition, 40)}")
            remaining = max(report.status.pending_count - len(report.entries), 0)
            if remaining > 0:
                lines.append(f"- (+{remaining} pieza/s publicable/s mas)")
        else:
            lines.append("- sin piezas autoaprobables para este slot")

        return "\n".join(lines)

    def _schedule_summary(self, target_date: date) -> EditorialDayPlanScheduleSummary:
        day_key = _WEEKDAY_TO_KEY[target_date.weekday()]
        day_schedule = self.schedule.day(day_key)
        if day_schedule is None:
            return EditorialDayPlanScheduleSummary(
                day_key=day_key,
                editorial_phase=str(self.phase_service.global_phase(target_date).phase),
            )
        return EditorialDayPlanScheduleSummary(
            day_key=day_key,
            editorial_phase=str(self.phase_service.global_phase(target_date).phase),
            publish_after=day_schedule.publish_after.strftime("%H:%M"),
            publish_slots=[slot.publish_after.strftime("%H:%M") for slot in day_schedule.slots],
            scheduled_types=sorted(day_schedule.types),
        )

    def _scheduled_content_types(self, target_date: date) -> list[str]:
        day_key = _WEEKDAY_TO_KEY[target_date.weekday()]
        day_schedule = self.schedule.day(day_key)
        if day_schedule is None:
            return []
        return list(sorted(day_schedule.types))

    def _slot_publish_limit(self, target_date: date) -> int:
        global_limit = max(int(self.settings.x_browser_release_action_limit), 1)
        day_key = _WEEKDAY_TO_KEY[target_date.weekday()]
        day_schedule = self.schedule.day(day_key)
        if day_schedule is None:
            return global_limit
        first_slot_limit = day_schedule.slots[0].publish_limit
        if first_slot_limit is None:
            return global_limit
        return min(global_limit, max(int(first_slot_limit), 1))

    def _published_reference_day_count(self, target_date: date, *, scheduled_types: set[str]) -> int:
        if not scheduled_types:
            return 0
        rows = self.session.execute(
            select(ContentCandidate.content_type, ContentCandidate.payload_json).where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.content_type.in_(sorted(scheduled_types)),
            )
        ).all()
        published_count = 0
        for content_type, payload_json in rows:
            if content_type not in scheduled_types:
                continue
            reference_date = None
            if isinstance(payload_json, dict):
                raw_reference_date = payload_json.get("reference_date")
                if isinstance(raw_reference_date, str):
                    try:
                        reference_date = date.fromisoformat(raw_reference_date)
                    except ValueError:
                        reference_date = None
            if reference_date == target_date:
                published_count += 1
        return published_count

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

    def _competition_label_for_candidate(self, candidate_id: int, *, fallback: str) -> str:
        candidate = self.session.get(ContentCandidate, candidate_id)
        if candidate is None:
            return fallback
        payload_json = candidate.payload_json or {}
        if isinstance(payload_json, dict):
            competition_name = payload_json.get("competition_name")
            if isinstance(competition_name, str) and competition_name.strip():
                return competition_name.strip()
        return fallback
