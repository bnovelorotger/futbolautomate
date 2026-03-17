from __future__ import annotations

from pathlib import Path

from app.schemas.draft_temp import DraftTempSnapshot


def render_draft_temp_sync(snapshot: DraftTempSnapshot, *, path: Path) -> str:
    return "\n".join(
        [
            f"path={path}",
            f"generated_at={snapshot.generated_at.isoformat()}",
            f"limit={snapshot.limit}",
            f"include_rejected={str(snapshot.include_rejected).lower()}",
            f"included_rows={snapshot.summary.included_rows}",
            f"draft_count={snapshot.summary.draft_count}",
            f"approved_count={snapshot.summary.approved_count}",
            f"published_count={snapshot.summary.published_count}",
            f"pending_export_count={snapshot.summary.pending_export_count}",
            f"capacity_deferred_count={snapshot.summary.capacity_deferred_count}",
        ]
    )
