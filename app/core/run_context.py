from __future__ import annotations

import contextvars
import uuid

_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="")


def set_run_id(run_id: str | None = None) -> str:
    rid = run_id or uuid.uuid4().hex[:8]
    _run_id.set(rid)
    return rid


def get_run_id() -> str:
    return _run_id.get()
