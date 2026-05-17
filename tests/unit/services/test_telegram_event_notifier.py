from __future__ import annotations

from datetime import UTC, datetime

from app.services.telegram_event_notifier import TelegramEventNotifier


class FakeTelegramNotificationService:
    def __init__(self, *, configured: bool = True, send_result: bool = True) -> None:
        self.configured = configured
        self.send_result = send_result
        self.messages: list[str] = []

    def is_configured(self) -> bool:
        return self.configured

    def send_message(self, text: str, *, parse_mode: str = "HTML") -> bool:
        self.messages.append(text)
        return self.send_result


def test_task_started_renders_expected_message_and_escapes_html() -> None:
    fake_service = FakeTelegramNotificationService()
    notifier = TelegramEventNotifier(notification_service=fake_service)

    result = notifier.task_started(
        task_name="editorial_release <prod>",
        mode="dry_run & verify",
        started_at="2026-05-17 09:00:00",
        summary_metrics={
            "items total": 4,
            "real ratio": 0.75,
            "fallback ratio": 0.25,
            "send ok": True,
            "ignored": None,
        },
    )

    assert result is True
    assert len(fake_service.messages) == 1
    message = fake_service.messages[0]
    assert "<b>futbolbalear - inicio tarea</b>" in message
    assert "- task: editorial_release &lt;prod&gt;" in message
    assert "- status: started" in message
    assert "- mode: dry_run &amp; verify" in message
    assert "- started_at: 2026-05-17 09:00:00" in message
    assert "- items_total: 4" in message
    assert "- real_ratio: 0.75" in message
    assert "- fallback_ratio: 0.25" in message
    assert "- send_ok: true" in message
    assert "ignored" not in message


def test_task_finished_formats_datetime_and_duration() -> None:
    fake_service = FakeTelegramNotificationService()
    notifier = TelegramEventNotifier(notification_service=fake_service)

    result = notifier.task_finished(
        task_name="refresh_data",
        mode="scheduled",
        started_at=datetime(2026, 5, 17, 7, 30, 5, tzinfo=UTC),
        duration_seconds=3661.8,
        summary_metrics={"found": 12, "inserted": 5, "updated": 3},
    )

    assert result is True
    message = fake_service.messages[0]
    assert "<b>futbolbalear - tarea completada</b>" in message
    assert "- started_at: 2026-05-17T07:30:05+00:00" in message
    assert "- duration: 01:01:01" in message
    assert "- found: 12" in message
    assert "- inserted: 5" in message
    assert "- updated: 3" in message


def test_task_failed_includes_reason_and_negative_duration_is_clamped() -> None:
    fake_service = FakeTelegramNotificationService()
    notifier = TelegramEventNotifier(notification_service=fake_service)

    result = notifier.task_failed(
        task_name="daily_digest",
        started_at="2026-05-17 22:00:00",
        duration_seconds=-5,
        error_message='timeout en "telegram"',
        summary_metrics={"failed": 1},
    )

    assert result is True
    message = fake_service.messages[0]
    assert "<b>futbolbalear - tarea con error</b>" in message
    assert "- reason: timeout en &quot;telegram&quot;" in message
    assert "- duration: 00:00:00" in message
    assert "- failed: 1" in message


def test_notifier_returns_false_without_sending_when_not_configured() -> None:
    fake_service = FakeTelegramNotificationService(configured=False)
    notifier = TelegramEventNotifier(notification_service=fake_service)

    result = notifier.task_started(task_name="editorial_release")

    assert result is False
    assert fake_service.messages == []


def test_notifier_propagates_send_result() -> None:
    fake_service = FakeTelegramNotificationService(send_result=False)
    notifier = TelegramEventNotifier(notification_service=fake_service)

    result = notifier.task_finished(task_name="editorial_release")

    assert result is False
    assert len(fake_service.messages) == 1
