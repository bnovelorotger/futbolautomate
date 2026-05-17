from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from html import escape

from app.services.telegram_notification_service import TelegramNotificationService

SummaryMetricValue = str | int | float | bool | None


@dataclass(frozen=True)
class TaskEventPayload:
    task_name: str
    title: str
    status: str
    mode: str | None = None
    started_at: datetime | str | None = None
    duration_seconds: float | int | None = None
    summary_metrics: Mapping[str, SummaryMetricValue] | None = None
    error_message: str | None = None


class TelegramEventNotifier:
    def __init__(
        self,
        *,
        notification_service: TelegramNotificationService | None = None,
    ) -> None:
        self._notification_service = notification_service or TelegramNotificationService()

    def is_configured(self) -> bool:
        return self._notification_service.is_configured()

    def task_started(
        self,
        *,
        task_name: str,
        mode: str | None = None,
        started_at: datetime | str | None = None,
        status: str = "started",
        summary_metrics: Mapping[str, SummaryMetricValue] | None = None,
    ) -> bool:
        return self._send_task_event(
            TaskEventPayload(
                task_name=task_name,
                title="inicio tarea",
                status=status,
                mode=mode,
                started_at=started_at,
                summary_metrics=summary_metrics,
            )
        )

    def task_finished(
        self,
        *,
        task_name: str,
        mode: str | None = None,
        started_at: datetime | str | None = None,
        duration_seconds: float | int | None = None,
        status: str = "ok",
        summary_metrics: Mapping[str, SummaryMetricValue] | None = None,
    ) -> bool:
        return self._send_task_event(
            TaskEventPayload(
                task_name=task_name,
                title="tarea completada",
                status=status,
                mode=mode,
                started_at=started_at,
                duration_seconds=duration_seconds,
                summary_metrics=summary_metrics,
            )
        )

    def task_failed(
        self,
        *,
        task_name: str,
        mode: str | None = None,
        started_at: datetime | str | None = None,
        duration_seconds: float | int | None = None,
        status: str = "error",
        summary_metrics: Mapping[str, SummaryMetricValue] | None = None,
        error_message: str | None = None,
    ) -> bool:
        return self._send_task_event(
            TaskEventPayload(
                task_name=task_name,
                title="tarea con error",
                status=status,
                mode=mode,
                started_at=started_at,
                duration_seconds=duration_seconds,
                summary_metrics=summary_metrics,
                error_message=error_message,
            )
        )

    def _send_task_event(self, payload: TaskEventPayload) -> bool:
        if not self.is_configured():
            return False
        return self._notification_service.send_message(self._render_message(payload))

    def _render_message(self, payload: TaskEventPayload) -> str:
        lines = [f"<b>futbolbalear - {escape(payload.title)}</b>"]
        lines.append(f"- task: {escape(payload.task_name)}")
        lines.append(f"- status: {escape(payload.status)}")

        if payload.mode:
            lines.append(f"- mode: {escape(payload.mode)}")
        if payload.started_at:
            lines.append(f"- started_at: {escape(self._format_started_at(payload.started_at))}")
        if payload.duration_seconds is not None:
            lines.append(f"- duration: {escape(self._format_duration(payload.duration_seconds))}")
        if payload.error_message:
            lines.append(f"- reason: {escape(payload.error_message)}")

        for key, value in self._normalized_metrics(payload.summary_metrics).items():
            lines.append(f"- {escape(key)}: {escape(value)}")

        return "\n".join(lines)

    def _normalized_metrics(
        self,
        summary_metrics: Mapping[str, SummaryMetricValue] | None,
    ) -> dict[str, str]:
        if not summary_metrics:
            return {}

        normalized: dict[str, str] = {}
        for key, value in summary_metrics.items():
            if value is None:
                continue
            metric_key = key.strip().replace(" ", "_")
            if not metric_key:
                continue
            normalized[metric_key] = self._format_metric_value(value)
        return normalized

    def _format_started_at(self, started_at: datetime | str) -> str:
        if isinstance(started_at, datetime):
            return started_at.isoformat(timespec="seconds")
        return started_at.strip()

    def _format_duration(self, duration_seconds: float | int) -> str:
        total_seconds = max(0, int(duration_seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _format_metric_value(self, value: SummaryMetricValue) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)
