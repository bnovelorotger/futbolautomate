from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime

from typer.testing import CliRunner

from app.pipelines import editorial_daily_digest
from app.schemas.editorial_daily_digest import (
    EditorialDailyDigestAlertItem,
    EditorialDailyDigestPublicationSummary,
    EditorialDailyDigestQueueSummary,
    EditorialDailyDigestReasonItem,
    EditorialDailyDigestReport,
    EditorialDailyDigestRewriteSummary,
)
from tests.unit.services.service_test_support import build_settings


class _FakeDigestService:
    def __init__(self) -> None:
        self.report = EditorialDailyDigestReport(
            reference_date=date(2026, 5, 18),
            start_date=date(2026, 5, 18),
            window_days=1,
            timezone="Europe/Madrid",
            generated_at=datetime(2026, 5, 18, 22, 0),
            publication=EditorialDailyDigestPublicationSummary(
                published_to_x=3,
                pending_dispatch=1,
                publication_errors=0,
                skipped_stale=0,
            ),
            queue=EditorialDailyDigestQueueSummary(
                draft_count=2,
                rejected_count=1,
                top_rejection_reasons=[EditorialDailyDigestReasonItem(code="quality_check_failed", count=1)],
                top_quality_errors=[EditorialDailyDigestReasonItem(code="rewrite_ai_cliche:en_resumen", count=1)],
            ),
            rewrite=EditorialDailyDigestRewriteSummary(
                total_rewrites=4,
                real_count=3,
                fallback_count=1,
                failed_count=0,
                other_count=0,
                real_ratio=0.75,
                fallback_ratio=0.25,
                failed_ratio=0.0,
                other_ratio=0.0,
                by_content_type={"preview": {"real": 2}, "viral_story": {"real": 1, "fallback_base_text": 1}},
            ),
            alerts=[EditorialDailyDigestAlertItem(level="WARNING", code="stuck_published", message="1 pendiente")],
        )

    def build_report(self, **_: object) -> EditorialDailyDigestReport:
        return self.report

    def render_console(self, report: EditorialDailyDigestReport) -> str:
        assert report is self.report
        return "console digest"

    def render_telegram(self, report: EditorialDailyDigestReport) -> str:
        assert report is self.report
        return "telegram digest"


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


def test_editorial_daily_digest_cli_dry_run_previews_telegram_without_sending(monkeypatch) -> None:
    cli = CliRunner()
    fake_service = _FakeDigestService()
    fake_notifier = _FakeNotifier()
    fake_telegram = _FakeTelegramService()

    monkeypatch.setattr(editorial_daily_digest, "get_settings", lambda: build_settings())
    monkeypatch.setattr(editorial_daily_digest, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(editorial_daily_digest, "init_db", lambda: None)
    monkeypatch.setattr(editorial_daily_digest, "session_scope", _fake_session_scope)
    monkeypatch.setattr(editorial_daily_digest, "_build_digest_service", lambda settings, session: fake_service)
    monkeypatch.setattr(editorial_daily_digest, "TelegramEventNotifier", lambda: fake_notifier)
    monkeypatch.setattr(
        editorial_daily_digest,
        "TelegramNotificationService",
        lambda settings=None: fake_telegram,
    )

    result = cli.invoke(editorial_daily_digest.app, ["--dry-run", "--send-telegram"])

    assert result.exit_code == 0
    assert "console digest" in result.output
    assert "[dry-run] Preview Telegram:" in result.output
    assert "telegram digest" in result.output
    assert fake_telegram.messages == []
    assert len(fake_notifier.started) == 1
    assert len(fake_notifier.finished) == 1
    assert fake_notifier.failed == []


def test_editorial_daily_digest_cli_sends_telegram_in_live_mode(monkeypatch) -> None:
    cli = CliRunner()
    fake_service = _FakeDigestService()
    fake_notifier = _FakeNotifier()
    fake_telegram = _FakeTelegramService()

    monkeypatch.setattr(editorial_daily_digest, "get_settings", lambda: build_settings())
    monkeypatch.setattr(editorial_daily_digest, "configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(editorial_daily_digest, "init_db", lambda: None)
    monkeypatch.setattr(editorial_daily_digest, "session_scope", _fake_session_scope)
    monkeypatch.setattr(editorial_daily_digest, "_build_digest_service", lambda settings, session: fake_service)
    monkeypatch.setattr(editorial_daily_digest, "TelegramEventNotifier", lambda: fake_notifier)
    monkeypatch.setattr(
        editorial_daily_digest,
        "TelegramNotificationService",
        lambda settings=None: fake_telegram,
    )

    result = cli.invoke(editorial_daily_digest.app, ["--send-telegram"])

    assert result.exit_code == 0
    assert fake_telegram.messages == ["telegram digest"]
    assert len(fake_notifier.started) == 1
    assert len(fake_notifier.finished) == 1
    assert fake_notifier.failed == []
