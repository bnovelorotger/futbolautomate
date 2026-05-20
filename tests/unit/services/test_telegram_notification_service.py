from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.services.telegram_notification_service import TelegramNotificationService

pytestmark = pytest.mark.real_telegram


def _settings(**overrides) -> Settings:
    base = {"database_url": "sqlite+pysqlite:///:memory:", "telegram_bot_token": None, "telegram_chat_id": None}
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------


def test_is_configured_true_when_both_values_set() -> None:
    settings = _settings(telegram_bot_token="tok", telegram_chat_id="123")
    svc = TelegramNotificationService(settings=settings)
    assert svc.is_configured() is True


def test_is_configured_false_when_token_missing() -> None:
    settings = _settings(telegram_chat_id="123")
    svc = TelegramNotificationService(settings=settings)
    assert svc.is_configured() is False


def test_is_configured_false_when_chat_id_missing() -> None:
    settings = _settings(telegram_bot_token="tok")
    svc = TelegramNotificationService(settings=settings)
    assert svc.is_configured() is False


def test_is_configured_false_when_both_missing() -> None:
    settings = _settings()
    svc = TelegramNotificationService(settings=settings)
    assert svc.is_configured() is False


# ---------------------------------------------------------------------------
# send_message — success path
# ---------------------------------------------------------------------------


def test_send_message_returns_true_on_200() -> None:
    settings = _settings(telegram_bot_token="tok", telegram_chat_id="123")
    svc = TelegramNotificationService(settings=settings)

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("app.services.telegram_notification_service.requests.post", return_value=mock_response) as mock_post:
        result = svc.send_message("hola")

    assert result is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["json"]["chat_id"] == "123"
    assert call_kwargs.kwargs["json"]["text"] == "hola"
    assert call_kwargs.kwargs["json"]["parse_mode"] == "HTML"


# ---------------------------------------------------------------------------
# send_message — failure paths (never raises)
# ---------------------------------------------------------------------------


def test_send_message_returns_false_on_non_200() -> None:
    settings = _settings(telegram_bot_token="tok", telegram_chat_id="123")
    svc = TelegramNotificationService(settings=settings)

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    with patch("app.services.telegram_notification_service.requests.post", return_value=mock_response):
        result = svc.send_message("hola")

    assert result is False


def test_send_message_returns_false_and_does_not_raise_on_exception() -> None:
    settings = _settings(telegram_bot_token="tok", telegram_chat_id="123")
    svc = TelegramNotificationService(settings=settings)

    with patch(
        "app.services.telegram_notification_service.requests.post",
        side_effect=ConnectionError("red caida"),
    ):
        result = svc.send_message("hola")

    assert result is False


def test_send_message_returns_false_when_not_configured() -> None:
    settings = _settings()
    svc = TelegramNotificationService(settings=settings)
    # No patch needed — should short-circuit before any HTTP call
    result = svc.send_message("hola")
    assert result is False


# ---------------------------------------------------------------------------
# get_updates
# ---------------------------------------------------------------------------


def test_get_updates_returns_result_list() -> None:
    settings = _settings(telegram_bot_token="tok")
    svc = TelegramNotificationService(settings=settings)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "ok": True,
        "result": [
            {"update_id": 1, "message": {"chat": {"id": 42}, "text": "hi"}},
        ],
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.telegram_notification_service.requests.get", return_value=mock_response):
        updates = svc.get_updates()

    assert len(updates) == 1
    assert updates[0]["message"]["chat"]["id"] == 42


def test_get_updates_returns_empty_list_when_token_missing() -> None:
    settings = _settings()
    svc = TelegramNotificationService(settings=settings)
    updates = svc.get_updates()
    assert updates == []


def test_get_updates_returns_empty_list_on_exception() -> None:
    settings = _settings(telegram_bot_token="tok")
    svc = TelegramNotificationService(settings=settings)

    with patch(
        "app.services.telegram_notification_service.requests.get",
        side_effect=TimeoutError("timeout"),
    ):
        updates = svc.get_updates()

    assert updates == []
