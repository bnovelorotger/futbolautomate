from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REFRESH_SCRIPT = ROOT / "scripts" / "windows" / "refresh_data.ps1"

PLAYOFF_COMPETITIONS = {
    "tercera_rfef_g11_playoff",
    "segunda_rfef_g3_playoff_ascenso",
    "segunda_rfef_g3_playoff_permanencia",
    "primera_rfef_playoff_ascenso",
    "tercera_femenina_g11_playoff",
    "division_honor_ibiza_playoff",
    "division_honor_menorca_playoff",
    "division_honor_mallorca_playoff",
}


def _ps_array_values(script: str, variable_name: str) -> set[str]:
    match = re.search(rf"\${variable_name}\s*=\s*@\((.*?)\)", script, flags=re.DOTALL)
    assert match is not None
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def test_refresh_data_ps1_refreshes_playoff_competitions_as_matches_only() -> None:
    script = REFRESH_SCRIPT.read_text(encoding="utf-8")

    assert _ps_array_values(script, "playoffCompetitions") == PLAYOFF_COMPETITIONS

    start = script.index("foreach ($competition in $playoffCompetitions)")
    end = script.index('Invoke-PythonModule -Label "enrich_match_events"', start)
    playoff_refresh_block = script[start:end]

    assert '"--target", "matches"' in playoff_refresh_block
    assert "standings" not in playoff_refresh_block
