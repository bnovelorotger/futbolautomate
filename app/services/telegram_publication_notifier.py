from __future__ import annotations

from datetime import datetime
from html import escape

from app.core.config import Settings, get_settings
from app.db.models import ContentCandidate
from app.services.telegram_notification_service import TelegramNotificationService


class TelegramPublicationNotifier:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        notification_service: TelegramNotificationService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._notification_service = notification_service or TelegramNotificationService(settings=self.settings)

    def is_enabled(self) -> bool:
        return self.settings.telegram_publication_notifications_enabled and self._notification_service.is_configured()

    def publication_succeeded(
        self,
        *,
        candidate: ContentCandidate,
        published_at: datetime,
        excerpt: str,
        selected_text_source: str | None = None,
    ) -> bool:
        if not self.is_enabled():
            return False
        message = self._render_publication_message(
            candidate=candidate,
            published_at=published_at,
            excerpt=excerpt,
            selected_text_source=selected_text_source,
        )
        return self._notification_service.send_message(message)

    def _render_publication_message(
        self,
        *,
        candidate: ContentCandidate,
        published_at: datetime,
        excerpt: str,
        selected_text_source: str | None,
    ) -> str:
        payload_json = candidate.payload_json or {}
        competition_name = payload_json.get("competition_name") if isinstance(payload_json, dict) else None
        reference_date = payload_json.get("reference_date") if isinstance(payload_json, dict) else None
        lines = ["<b>futbolbalear - post publicado</b>"]
        lines.append(f"- id: {candidate.id}")
        lines.append(f"- type: {escape(candidate.content_type)}")
        if isinstance(competition_name, str) and competition_name.strip():
            lines.append(f"- competition: {escape(competition_name.strip())}")
        if isinstance(reference_date, str) and reference_date.strip():
            lines.append(f"- reference_date: {escape(reference_date.strip())}")
        lines.append(f"- published_at: {escape(self._format_datetime(published_at))}")
        if selected_text_source:
            lines.append(f"- text_source: {escape(selected_text_source)}")
        lines.append(f"- excerpt: {escape(excerpt)}")
        return "\n".join(lines)

    def _format_datetime(self, value: datetime) -> str:
        return value.isoformat(timespec="seconds")
