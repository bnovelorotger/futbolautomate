from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from app.core.run_context import get_run_id

_STANDARD_RECORD_ATTRS = set(logging.makeLogRecord({}).__dict__.keys())


class RunIdFilter(logging.Filter):
    """Inject the current run_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = get_run_id() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": getattr(record, "run_id", None) or "-",
        }
        for key in ("source", "competition", "target", "url", "records_found"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS or key in payload or key.startswith("_"):
                continue
            if isinstance(value, (str, int, float, bool)) or value is None or isinstance(value, (list, dict)):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


class TextWithExtrasFormatter(logging.Formatter):
    """Plain text formatter that appends `extra={...}` fields after the message.

    Keeps logs human-readable while exposing structured fields like
    `rows_total_sql`, `rows_eligible`, `dispatched_ids` that would otherwise
    only be visible in JSON mode.
    """

    BASE_FORMAT = "%(asctime)s | %(levelname)s | [%(run_id)s] | %(name)s | %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(self) -> None:
        super().__init__(fmt=self.BASE_FORMAT, datefmt=self.DATE_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {}
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS or key in {"run_id"} or key.startswith("_"):
                continue
            if isinstance(value, (str, int, float, bool)) or value is None or isinstance(value, (list, dict)):
                extras[key] = value
        if not extras:
            return base
        try:
            suffix = json.dumps(extras, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            suffix = str(extras)
        return f"{base} | {suffix}"


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    run_id_filter = RunIdFilter()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(run_id_filter)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextWithExtrasFormatter())
    root.addHandler(handler)
