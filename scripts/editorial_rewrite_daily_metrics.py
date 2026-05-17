from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.run_context import set_run_id
from app.db.session import init_db, session_scope
from app.services.editorial_rewrite_metrics import EditorialRewriteMetricsService


def _default_output_path() -> Path:
    return Path(__file__).resolve().parents[1] / "logs" / "editorial_rewrite_daily_metrics.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Metricas diarias de rewrite real vs fallback.")
    parser.add_argument("--start-date", help="Fecha inicial local YYYY-MM-DD")
    parser.add_argument("--end-date", help="Fecha final local YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=7, help="Ventana local si no se pasan fechas")
    parser.add_argument("--competition-slug", default=None, help="Filtra por competicion")
    parser.add_argument("--output", type=Path, default=None, help="Guarda el JSON en disco")
    args = parser.parse_args()

    set_run_id()
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_db()

    if args.start_date and args.end_date:
        start_date = date.fromisoformat(args.start_date)
        end_date = date.fromisoformat(args.end_date)
    else:
        from datetime import timedelta

        today = datetime.now(ZoneInfo(settings.timezone)).date()
        start_date = today - timedelta(days=max(args.days, 1) - 1)
        end_date = today

    with session_scope() as session:
        payload = EditorialRewriteMetricsService(session, settings=settings).daily_outcome_report(
            start_date=start_date,
            end_date=end_date,
            competition_slug=args.competition_slug,
        )

    output = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
