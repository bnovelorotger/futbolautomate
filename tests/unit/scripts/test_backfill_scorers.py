from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "windows" / "backfill_scorers.ps1"
STATS_SCRIPT = ROOT / "scripts" / "windows" / "backfill_stats.ps1"
SCHEDULER_SCRIPT = ROOT / "scripts" / "windows" / "setup_scheduler.ps1"


def test_backfill_scorers_runs_match_events_for_regular_competitions() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "tercera_rfef_g11" in script
    assert "segunda_rfef_g3_baleares" in script
    assert "tercera_rfef_g11_playoff" not in script
    assert '"match_events"' in script
    assert '"enrich-pending"' in script
    assert '"--season", $Season' in script
    assert '"--limit", "$LimitPerCompetition"' in script
    assert '$arguments += "--dry-run"' in script


def test_backfill_stats_reports_base_coverage_and_detail_backfill() -> None:
    script = STATS_SCRIPT.read_text(encoding="utf-8")

    assert '"stat_coverage", "report"' in script
    assert '"match_events"' in script
    assert '"enrich-pending"' in script
    assert '$effectiveDataTypes' in script
    assert '"--season", $Season' in script
    assert '"--limit", "$LimitPerCompetition"' in script


def test_setup_scheduler_registers_weekly_stats_backfill() -> None:
    script = SCHEDULER_SCRIPT.read_text(encoding="utf-8")

    assert "futbol_scorer_backfill_weekly" in script
    assert "futbol_stats_backfill_weekly" in script
    assert "scripts\\windows\\backfill_stats.ps1" in script
    assert "-Season 2025-26 -DataTypes results,standings,scorers,halftime -LimitPerCompetition 250 -IncludeErrors" in script
