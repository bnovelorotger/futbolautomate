from __future__ import annotations

import json
from pathlib import Path

from app.schemas.draft_temp import DraftTempSnapshot


def draft_temp_path() -> Path:
    return Path(__file__).resolve().parents[2] / "logs" / "draft_temp.json"


def load_draft_temp_snapshot(path: Path | None = None) -> DraftTempSnapshot | None:
    snapshot_path = path or draft_temp_path()
    if not snapshot_path.exists():
        return None
    with snapshot_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return DraftTempSnapshot.model_validate(payload)


def store_draft_temp_snapshot(
    snapshot: DraftTempSnapshot,
    path: Path | None = None,
) -> Path:
    snapshot_path = path or draft_temp_path()
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with snapshot_path.open("w", encoding="utf-8") as handle:
        json.dump(snapshot.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
    return snapshot_path
