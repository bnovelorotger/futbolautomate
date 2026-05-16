from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.channels.x_browser.publisher import XBrowserPublisher, XBrowserPublishError


def test_publish_text_dry_run_returns_response_without_browser() -> None:
    publisher = XBrowserPublisher(Path("nonexistent.json"), headless=True)

    response = publisher.publish_text("Hello Balear", dry_run=True)

    assert response.dry_run is True
    assert response.text == "Hello Balear"
    assert response.published_at is None


def test_publish_text_dry_run_logs_image_when_provided(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    image_file = tmp_path / "standings_roundup_1.png"
    image_file.write_bytes(b"\x89PNG\r\n")
    publisher = XBrowserPublisher(Path("nonexistent.json"), headless=True)

    with caplog.at_level(logging.INFO, logger="app.channels.x_browser.publisher"):
        response = publisher.publish_text("Tabla clasificación", image_path=image_file, dry_run=True)

    assert response.dry_run is True
    assert any("standings_roundup_1.png" in record.message for record in caplog.records)


def test_publish_text_dry_run_skips_image_log_when_file_missing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    missing = tmp_path / "does_not_exist.png"
    publisher = XBrowserPublisher(Path("nonexistent.json"), headless=True)

    with caplog.at_level(logging.INFO, logger="app.channels.x_browser.publisher"):
        response = publisher.publish_text("Tabla clasificación", image_path=missing, dry_run=True)

    assert response.dry_run is True
    assert not any("does_not_exist.png" in record.message for record in caplog.records)


def test_publish_text_raises_on_empty_text() -> None:
    publisher = XBrowserPublisher(Path("nonexistent.json"), headless=True)

    with pytest.raises(XBrowserPublishError, match="cannot be empty"):
        publisher.publish_text("", dry_run=True)


def test_publish_text_raises_on_text_exceeding_limit() -> None:
    publisher = XBrowserPublisher(Path("nonexistent.json"), headless=True)
    long_text = "x" * 281

    with pytest.raises(XBrowserPublishError, match="exceeds"):
        publisher.publish_text(long_text, dry_run=True)


def test_publish_text_accepts_image_path_none_in_dry_run() -> None:
    publisher = XBrowserPublisher(Path("nonexistent.json"), headless=True)

    response = publisher.publish_text("Sin imagen", image_path=None, dry_run=True)

    assert response.dry_run is True
    assert response.image_path is None
