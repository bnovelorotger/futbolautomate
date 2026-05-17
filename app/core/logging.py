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
            if isinstance(value, (str, int, float, bool)) or value is None:
                payload[key] = value
            elif isinstance(value, (list, dict)):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


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
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | [%(run_id)s] | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    root.addHandler(handler)
