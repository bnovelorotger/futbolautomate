from __future__ import annotations

import pytest

from tests.helpers import read_fixture

__all__ = ["read_fixture"]


@pytest.fixture(autouse=True)
def _block_real_telegram(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    # Prevent any test from hitting the real Telegram API. Tests that exercise
    # TelegramNotificationService itself opt out via the `real_telegram` marker
    # (and still patch `requests` locally).
    if request.node.get_closest_marker("real_telegram"):
        return

    def _noop_send_message(self, text, *, parse_mode="HTML"):  # type: ignore[no-untyped-def]
        return True

    def _noop_get_updates(self):  # type: ignore[no-untyped-def]
        return []

    monkeypatch.setattr(
        "app.services.telegram_notification_service.TelegramNotificationService.send_message",
        _noop_send_message,
    )
    monkeypatch.setattr(
        "app.services.telegram_notification_service.TelegramNotificationService.get_updates",
        _noop_get_updates,
    )
