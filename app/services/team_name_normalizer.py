from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings


def _aliases_path() -> Path:
    return get_settings().app_root / "app" / "config" / "team_name_aliases.json"


@lru_cache(maxsize=1)
def load_team_name_aliases() -> dict[str, str]:
    path = _aliases_path()
    if not path.exists():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}

    aliases: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        raw_key = key.strip()
        raw_value = value.strip()
        if not raw_key or not raw_value:
            continue
        aliases[raw_key] = raw_value
    return aliases


def normalize_team_name(name: str) -> str:
    original = name.strip()
    if not original:
        return name
    return load_team_name_aliases().get(original, original)
