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
            f"phase3_only={str(snapshot.phase3_only).lower()}",
            f"recompute_quality_checks={str(snapshot.recompute_quality_checks).lower()}",
            f"phase3_candidate_count={snapshot.summary.phase3_candidate_count}",
            f"phase3_eligible_count={snapshot.summary.phase3_eligible_count}",
            f"phase3_quality_passed_count={snapshot.summary.phase3_quality_passed_count}",
            f"phase3_quality_failed_count={snapshot.summary.phase3_quality_failed_count}",
        ]
    )
