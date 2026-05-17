from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from app.core.config import get_settings
from app.core.draft_temp import store_draft_temp_snapshot
from app.core.logging import configure_logging
from app.core.run_context import set_run_id
from app.db.session import init_db, session_scope
from app.services.draft_temp_service import DraftTempService
from app.services.editorial_release_pipeline import EditorialReleasePipelineService


def _default_output_path() -> Path:
    return Path(__file__).resolve().parents[1] / "logs" / "draft_temp_phase3.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Readiness de fase 3 para humanized_local: dry-run de release y snapshot enriquecido.",
    )
    parser.add_argument("--date", dest="reference_date", default=None, help="Fecha local YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=200, help="Maximo de candidatos a revisar")
    parser.add_argument(
        "--use-draft",
        action="store_true",
        help="Usa text_draft al recomputar quality checks del snapshot",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_output_path(),
        help="Ruta del snapshot JSON de fase 3",
    )
    args = parser.parse_args()

    set_run_id()
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_db()
    prefer_rewrite = not args.use_draft
    parsed_date = date.fromisoformat(args.reference_date) if args.reference_date else None

    with session_scope() as session:
        release_result = EditorialReleasePipelineService(session, settings=settings).run(
            reference_date=parsed_date,
            limit=args.limit,
            dry_run=True,
            prefer_rewrite=prefer_rewrite,
            publish_to_x=False,
            publish_via_typefully=False,
            publish_via_browser=False,
        )
        snapshot = DraftTempService(session, settings=settings).build_snapshot(
            limit=args.limit,
            include_rejected=False,
            phase3_only=True,
            recompute_quality_checks=True,
            prefer_rewrite=prefer_rewrite,
        )

    output_path = store_draft_temp_snapshot(snapshot, path=args.output)
    payload = {
        "flags": {
            "editorial_rewrite_humanized_local_enabled": settings.editorial_rewrite_humanized_local_enabled,
            "editorial_phase3_rollout_enabled": settings.editorial_phase3_rollout_enabled,
        },
        "release_dry_run": {
            "drafts_found": release_result.drafts_found,
            "autoapprovable_count": release_result.autoapprovable_count,
            "autoapproved_count": release_result.autoapproved_count,
            "manual_review_count": release_result.manual_review_count,
            "dispatched_count": release_result.dispatched_count,
            "export_base_total_items": release_result.export_base_total_items,
        },
        "phase3_snapshot_path": str(output_path),
        "phase3_snapshot_summary": snapshot.summary.model_dump(mode="json"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
