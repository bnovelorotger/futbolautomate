"""Run a single scraper and print detailed results or errors."""
import traceback
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

try:
    from app.pipelines.runner import run_source_pipeline
    from app.core.enums import TargetType, SourceName
    result = run_source_pipeline(
        source=SourceName.FUTBOLME,
        target=TargetType.MATCHES,
        competition_code="tercera_rfef_g11",
        dry_run=False,
    )
    print("SUCCESS:", result)
except Exception:
    traceback.print_exc()
