[CmdletBinding()]
param(
    [string]$Season = "2025-26",
    [int]$LimitPerCompetition = 250,
    [switch]$IncludeErrors,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

$competitions = @(
    "tercera_rfef_g11",
    "segunda_rfef_g3_baleares",
    "primera_rfef_baleares",
    "division_honor_mallorca",
    "tercera_federacion_femenina_g11",
    "division_honor_ibiza_form",
    "division_honor_menorca"
)

Initialize-Runtime -LogName "cron_scorer_backfill.log" -SlotName "cron_scorer_backfill"

try {
    Write-Log -Level "INFO" -Message "=== backfill_scorers.ps1 season=$Season limit=$LimitPerCompetition include_errors=$IncludeErrors dry_run=$DryRun ==="

    foreach ($competition in $competitions) {
        $arguments = @(
            "match_events",
            "enrich-pending",
            "--competition", $competition,
            "--season", $Season,
            "--limit", "$LimitPerCompetition"
        )
        if ($IncludeErrors) {
            $arguments += "--include-errors"
        }
        if ($DryRun) {
            $arguments += "--dry-run"
        }

        Invoke-PythonModule -Label "backfill_scorers_${competition}" -Module "app.pipelines.runner" -Arguments $arguments
    }

    Complete-Script
    exit 0
}
catch {
    Fail-Script -ErrorRecord $_
    exit 1
}
finally {
    Release-Lock
}
