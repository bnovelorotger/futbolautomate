from __future__ import annotations

from typer.testing import CliRunner

from app.core.config import Settings
from app.pipelines import runner


class FakeTelegramService:
    def __init__(
        self,
        *,
        send_result: bool = True,
        updates: list[dict] | None = None,
    ) -> None:
        self.send_result = send_result
        self.updates = updates or []
        self.sent_messages: list[str] = []

    def send_message(self, text: str, *, parse_mode: str = "HTML") -> bool:
        self.sent_messages.append(text)
        return self.send_result

    def get_updates(self) -> list[dict]:
        return list(self.updates)


def _settings() -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        telegram_bot_token="tok",
        telegram_chat_id="123",
    )


def test_telegram_setup_cli_prints_unique_chat_ids(monkeypatch) -> None:
    cli = CliRunner()
    fake_service = FakeTelegramService(
        updates=[
            {"message": {"chat": {"id": 42}}},
            {"callback_query": {"message": {"chat": {"id": 99}}}},
            {"message": {"chat": {"id": 42}}},
        ]
    )

    monkeypatch.setattr(runner, "get_settings", _settings)
    monkeypatch.setattr(runner, "TelegramNotificationService", lambda settings=None: fake_service)

    result = cli.invoke(runner.app, ["telegram_notify", "setup"])

    assert result.exit_code == 0
    assert result.output.count("Chat ID encontrado: 42") == 1
    assert result.output.count("Chat ID encontrado: 99") == 1


def test_telegram_setup_cli_warns_when_no_updates(monkeypatch) -> None:
    cli = CliRunner()
    fake_service = FakeTelegramService(updates=[])

    monkeypatch.setattr(runner, "get_settings", _settings)
    monkeypatch.setattr(runner, "TelegramNotificationService", lambda settings=None: fake_service)

    result = cli.invoke(runner.app, ["telegram_notify", "setup"])

    assert result.exit_code == 0
    assert "No se encontraron actualizaciones." in result.output
    assert "Asegurate de haber enviado un mensaje al bot" in result.output


def test_telegram_test_cli_sends_message_and_returns_zero(monkeypatch) -> None:
    cli = CliRunner()
    fake_service = FakeTelegramService(send_result=True)

    monkeypatch.setattr(runner, "get_settings", _settings)
    monkeypatch.setattr(runner, "TelegramNotificationService", lambda settings=None: fake_service)

    result = cli.invoke(runner.app, ["telegram_notify", "test", "hola telegram"])

    assert result.exit_code == 0
    assert fake_service.sent_messages == ["hola telegram"]
    assert "Mensaje enviado correctamente." in result.output


def test_telegram_test_cli_returns_error_when_send_fails(monkeypatch) -> None:
    cli = CliRunner()
    fake_service = FakeTelegramService(send_result=False)

    monkeypatch.setattr(runner, "get_settings", _settings)
    monkeypatch.setattr(runner, "TelegramNotificationService", lambda settings=None: fake_service)

    result = cli.invoke(runner.app, ["telegram_notify", "test", "hola telegram"])

    assert result.exit_code == 1
    assert fake_service.sent_messages == ["hola telegram"]
    assert "Error al enviar el mensaje." in result.output
