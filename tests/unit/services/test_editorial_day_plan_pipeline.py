from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime

from typer.testing import CliRunner

from app.pipelines import editorial_day_plan
from app.schemas.editorial_day_plan import (
    EditorialDayPlanEntry,
    EditorialDayPlanReport,
    EditorialDayPlanScheduleSummary,
    EditorialDayPlanStatusSummary,
    EditorialDayPlanTypeItem,
)
from tests.unit.services.service_test_support import build_settings


class _FakePlanService:
    def __init__(self) -> None:
        self.report = EditorialDayPlanReport(
            target_date=date(2026, 5, 18),
            timezone="Europe/Madrid",
            generated_at=datetime(2026, 5, 18, 9, 0),
            schedule=EditorialDayPlanScheduleSummary(
                day_key="lunes",
                publish_after="09:00",
                scheduled_types=["results_roundup", "standings_roundup"],
            ),
            status=EditorialDayPlanStatusSummary(
                total_candidates=3,
                published_count=1,
                approved_count=1,
                draft_count=1,
                rejected_count=0,
                pending_count=2,
            ),
            by_content_type=[
                EditorialDayPlanTypeItem(content_type="preview", count=2),
                EditorialDayPlanTypeItem(content_type="viral_story", count=1),
            ],
            entries=[
                EditorialDayPlanEntry(
                    id=1,
                    status="approved",
                    content_type="preview",
                    competition="DH Mallorca",
                    priority=10,
                )
            ],
        )

    def build_report(self, **_: object) -> EditorialDayPlanReport:
        return self.report

    def render_console(self, report: EditorialDayPlanReport) -> str:
        assert report is self.report
        return "console plan"

    def render_telegram(self, report: EditorialDayPlanReport) -> str:
        assert report is self.report
        return "telegram plan"


class _FakeTelegramService:
    def __init__(self, configured: bool = True) -> None:
        self.configured = configured
        self.messages: list[str] = []

    def is_configured(self) -> bool:
        return self.configured

    def send_message(self, text: str, *, parse_mode: str = "HTML") -> bool:
        self.messages.append(text)
        return True


class _FakeNotifier:
    def __init__(self, configured: bool = True) -> None:
        self.configured = configured
        self.started: list[dict[str, object]] = []
        self.finished: list[dict[str, object]] = []
        self.failed: list[dict[str, object]] = []

    def is_configured(self) -> bool:
        return self.configured

    def task_started(self, **kwargs: object) -> bool:
        self.started.append(kwargs)
        return True

    def task_finished(self, **kwargs: object) -> bool:
        self.finished.append(kwargs)
        return True

    def task_failed(self, **kwargs: object) -> bool:
        self.failed.append(kwargs)
        return True


@contextmanager
def _fake_session_scope():
    yield object()


def test_editorial_day_plan_cli_dry_run_previews_telegram_without_sending(monkeypatch) -> None:
    cli = CliRunner()
    fake_service = _FakePlanService()
    fake_notifier = _FakeNotifier()
    fake_telegram = _FakeTelegramService()

    monkeypatch.setattr(editorial_day_plan, "get_settings", lambda: build_settings())
    monkeypatch.setattr(editorial_day_plan, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(editorial_day_plan, "init_db", lambda: None)
    monkeypatch.setattr(editorial_day_plan, "session_scope", _fake_session_scope)
    monkeypatch.setattr(editorial_day_plan, "_build_plan_service", lambda settings, session: fake_service)
    monkeypatch.setattr(editorial_day_plan, "TelegramEventNotifier", lambda: fake_notifier)
    monkeypatch.setattr(editorial_day_plan, "TelegramNotificationService", lambda settings=None: fake_telegram)

    result = cli.invoke(editorial_day_plan.app, ["--dry-run", "--send-telegram"])

    assert result.exit_code == 0
    assert "console plan" in result.output
    assert "[dry-run] Preview Telegram:" in result.output
    assert "telegram plan" in result.output
    assert fake_telegram.messages == []
    assert len(fake_notifier.started) == 1
    assert len(fake_notifier.finished) == 1
    assert fake_notifier.failed == []


def test_editorial_day_plan_cli_sends_telegram_in_live_mode(monkeypatch) -> None:
    cli = CliRunner()
    fake_service = _FakePlanService()
    fake_notifier = _FakeNotifier()
    fake_telegram = _FakeTelegramService()

    monkeypatch.setattr(editorial_day_plan, "get_settings", lambda: build_settings())
    monkeypatch.setattr(editorial_day_plan, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(editorial_day_plan, "init_db", lambda: None)
    monkeypatch.setattr(editorial_day_plan, "session_scope", _fake_session_scope)
    monkeypatch.setattr(editorial_day_plan, "_build_plan_service", lambda settings, session: fake_service)
    monkeypatch.setattr(editorial_day_plan, "TelegramEventNotifier", lambda: fake_notifier)
    monkeypatch.setattr(editorial_day_plan, "TelegramNotificationService", lambda settings=None: fake_telegram)

    result = cli.invoke(editorial_day_plan.app, ["--send-telegram"])

    assert result.exit_code == 0
    assert fake_telegram.messages == ["telegram plan"]
    assert len(fake_notifier.started) == 1
    assert len(fake_notifier.finished) == 1
    assert fake_notifier.failed == []
