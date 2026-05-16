from __future__ import annotations

import logging
from typing import Any

import requests

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class TelegramNotificationService:
    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """True if both token and chat_id are set."""
        return bool(self._settings.telegram_bot_token and self._settings.telegram_chat_id)

    def send_message(self, text: str, *, parse_mode: str = "HTML") -> bool:
        """Send a message to the configured chat. Returns True on success, False on failure (never raises)."""
        if not self.is_configured():
            logger.warning("TelegramNotificationService: no configurado (faltan token o chat_id)")
            return False
        try:
            url = self._api_url("sendMessage")
            payload: dict[str, Any] = {
                "chat_id": self._settings.telegram_chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            logger.error(
                "TelegramNotificationService: respuesta inesperada status=%s body=%s",
                response.status_code,
                response.text[:200],
            )
            return False
        except Exception as exc:
            logger.error("TelegramNotificationService: error al enviar mensaje: %s", exc)
            return False

    def get_updates(self) -> list[dict]:
        """Call getUpdates to discover chat_ids. Returns raw update list."""
        if not self._settings.telegram_bot_token:
            logger.warning("TelegramNotificationService: TELEGRAM_BOT_TOKEN no configurado")
            return []
        try:
            url = self._api_url("getUpdates")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("result", [])
        except Exception as exc:
            logger.error("TelegramNotificationService: error en getUpdates: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _api_url(self, method: str) -> str:
        token = self._settings.telegram_bot_token or ""
        base = self.BASE_URL.format(token=token)
        return f"{base}/{method}"
