from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.schemas.editorial_daily_digest import (
    EditorialDailyDigestAlertItem,
    EditorialDailyDigestPublicationSummary,
    EditorialDailyDigestQueueSummary,
    EditorialDailyDigestReasonItem,
    EditorialDailyDigestReport,
    EditorialDailyDigestRewriteSummary,
)
from app.services.editorial_rewrite_metrics import EditorialRewriteMetricsService
from app.services.pipeline_summary_service import PipelineSummaryService

_DEFAULT_TOP_REASON_LIMIT = 3


class EditorialDailyDigestService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        top_reason_limit: int = _DEFAULT_TOP_REASON_LIMIT,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.timezone = ZoneInfo(self.settings.timezone)
        self.top_reason_limit = top_reason_limit
        self.pipeline_summary = PipelineSummaryService(session, settings=self.settings)
        self.rewrite_metrics = EditorialRewriteMetricsService(session, settings=self.settings)

    def build_report(
        self,
        reference_date: date | None = None,
        window_days: int = 1,
    ) -> EditorialDailyDigestReport:
        ref_date = reference_date or datetime.now(self.timezone).date()
        start_date = ref_date - timedelta(days=max(window_days, 1) - 1)

        pipeline_report = self.pipeline_summary.summary(reference_date=ref_date, window_days=window_days)
        rewrite_report = self.rewrite_metrics.daily_outcome_report(
            start_date=start_date,
            end_date=ref_date,
        )

        return EditorialDailyDigestReport(
            reference_date=ref_date,
            start_date=start_date,
            window_days=window_days,
            timezone=self.settings.timezone,
            generated_at=self._localize_datetime(pipeline_report.generated_at),
            publication=EditorialDailyDigestPublicationSummary(
                published_to_x=pipeline_report.publication.published_to_x,
                pending_dispatch=pipeline_report.publication.pending_dispatch,
                publication_errors=pipeline_report.publication.publication_errors,
                skipped_stale=pipeline_report.publication.skipped_stale,
            ),
            queue=EditorialDailyDigestQueueSummary(
                draft_count=pipeline_report.blocked.draft_count,
                rejected_count=pipeline_report.blocked.rejected_count,
                top_rejection_reasons=self._top_reason_items(pipeline_report.blocked.rejection_reason_counts),
                top_quality_errors=self._top_reason_items(pipeline_report.blocked.quality_error_counts),
            ),
            rewrite=EditorialDailyDigestRewriteSummary(
                total_rewrites=int(rewrite_report["total_rewrites"]),
                real_count=int(rewrite_report["real_count"]),
                fallback_count=int(rewrite_report["fallback_count"]),
                failed_count=int(rewrite_report["failed_count"]),
                other_count=int(rewrite_report["other_count"]),
                real_ratio=float(rewrite_report["real_ratio"]),
                fallback_ratio=float(rewrite_report["fallback_ratio"]),
                failed_ratio=float(rewrite_report["failed_ratio"]),
                other_ratio=float(rewrite_report["other_ratio"]),
                by_content_type={
                    str(content_type): {str(outcome): int(count) for outcome, count in outcomes.items()}
                    for content_type, outcomes in rewrite_report["by_content_type"].items()
                },
            ),
            alerts=[
                EditorialDailyDigestAlertItem(level=alert.level, code=alert.code, message=alert.message)
                for alert in pipeline_report.alerts
            ],
        )

    def render_console(self, report: EditorialDailyDigestReport) -> str:
        lines = [
            f"futbolbalear - cierre diario {report.reference_date.isoformat()}",
            f"Ventana: {report.start_date.isoformat()} -> {report.reference_date.isoformat()} ({report.window_days} dia/s)",
            "",
            "Publicacion",
            f"- publicados en X: {report.publication.published_to_x}",
            f"- pendientes de dispatch/publicacion: {report.publication.pending_dispatch}",
            f"- errores de publicacion: {report.publication.publication_errors}",
        ]
        if report.publication.skipped_stale:
            lines.append(f"- skipped stale: {report.publication.skipped_stale}")

        lines.extend(
            [
                "",
                "Cola editorial",
                f"- drafts: {report.queue.draft_count}",
                f"- rejected: {report.queue.rejected_count}",
            ]
        )
        rejection_summary = self._render_reason_block(
            "Top motivos de rechazo",
            report.queue.top_rejection_reasons,
        )
        quality_summary = self._render_reason_block(
            "Top quality errors",
            report.queue.top_quality_errors,
        )
        if rejection_summary:
            lines.extend(["", rejection_summary])
        if quality_summary:
            lines.extend(["", quality_summary])

        lines.extend(
            [
                "",
                "Rewrite fase 3",
                f"- total: {report.rewrite.total_rewrites}",
                f"- real: {report.rewrite.real_count} ({self._format_ratio(report.rewrite.real_ratio)})",
                f"- fallback: {report.rewrite.fallback_count} ({self._format_ratio(report.rewrite.fallback_ratio)})",
                f"- failed: {report.rewrite.failed_count} ({self._format_ratio(report.rewrite.failed_ratio)})",
            ]
        )
        if report.rewrite.other_count:
            lines.append(f"- other: {report.rewrite.other_count} ({self._format_ratio(report.rewrite.other_ratio)})")

        lines.extend(["", "Alertas activas"])
        if report.alerts:
            lines.extend(f"- [{alert.level}] {alert.message}" for alert in report.alerts)
        else:
            lines.append("- sin alertas activas")

        lines.extend(
            [
                "",
                f"Generado: {self._format_datetime(report.generated_at)} ({report.timezone})",
            ]
        )
        return "\n".join(lines)

    def render_telegram(self, report: EditorialDailyDigestReport) -> str:
        lines = [
            f"futbolbalear - cierre diario {report.reference_date.isoformat()}",
            "",
            "Publicacion",
            f"- publicados en X: {report.publication.published_to_x}",
            f"- pendientes: {report.publication.pending_dispatch}",
            f"- errores: {report.publication.publication_errors}",
            "",
            "Rewrite fase 3",
            f"- real: {report.rewrite.real_count} ({self._format_ratio(report.rewrite.real_ratio)})",
            f"- fallback: {report.rewrite.fallback_count} ({self._format_ratio(report.rewrite.fallback_ratio)})",
            f"- failed: {report.rewrite.failed_count} ({self._format_ratio(report.rewrite.failed_ratio)})",
            "",
            "Cola",
            f"- drafts: {report.queue.draft_count}",
            f"- rejected: {report.queue.rejected_count}",
        ]

        if report.queue.top_rejection_reasons:
            lines.append(
                "- rechazo top: "
                + ", ".join(f"{item.code} ({item.count})" for item in report.queue.top_rejection_reasons)
            )
        if report.queue.top_quality_errors:
            lines.append(
                "- quality top: "
                + ", ".join(f"{item.code} ({item.count})" for item in report.queue.top_quality_errors)
            )

        lines.extend(["", "Alertas"])
        if report.alerts:
            for alert in report.alerts[: self.top_reason_limit]:
                lines.append(f"- [{alert.level}] {self._truncate(alert.message, 100)}")
            remaining = len(report.alerts) - self.top_reason_limit
            if remaining > 0:
                lines.append(f"- (+{remaining} alerta/s mas)")
        else:
            lines.append("- sin alertas activas")

        return "\n".join(lines)

    def _top_reason_items(self, counts: dict[str, int]) -> list[EditorialDailyDigestReasonItem]:
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [
            EditorialDailyDigestReasonItem(code=str(code), count=int(count))
            for code, count in ordered[: self.top_reason_limit]
            if int(count) > 0
        ]

    def _render_reason_block(self, title: str, items: list[EditorialDailyDigestReasonItem]) -> str:
        if not items:
            return ""
        lines = [title]
        lines.extend(f"- {item.code}: {item.count}" for item in items)
        return "\n".join(lines)

    def _format_ratio(self, value: float) -> str:
        return f"{value:.0%}"

    def _localize_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).astimezone(self.timezone)
        return value.astimezone(self.timezone)

    def _format_datetime(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M")

    def _truncate(self, value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: max(limit - 3, 0)].rstrip() + "..."
