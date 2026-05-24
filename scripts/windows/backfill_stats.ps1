[CmdletBinding()]
param(
    [string]$Season = "2025-26",
    [string[]]$DataTypes = @("results", "standings", "scorers"),
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

$effectiveDataTypes = @()
foreach ($item in $DataTypes) {
    $effectiveDataTypes += $item.Split(",") |
        ForEach-Object { $_.Trim().ToLowerInvariant() } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
}
$effectiveDataTypes = @($effectiveDataTypes | Select-Object -Unique)

Initialize-Runtime -LogName "cron_stats_backfill.log" -SlotName "cron_stats_backfill"

try {
    Write-Log -Level "INFO" -Message "=== backfill_stats.ps1 season=$Season data_types=$($effectiveDataTypes -join ',') limit=$LimitPerCompetition include_errors=$IncludeErrors dry_run=$DryRun ==="

    foreach ($competition in $competitions) {
        if ($effectiveDataTypes -contains "results" -or $effectiveDataTypes -contains "standings") {
            Invoke-PythonModule `
                -Label "stat_coverage_${competition}" `
                -Module "app.pipelines.runner" `
                -Arguments @("stat_coverage", "report", "--competition", $competition, "--season", $Season)
        }

        if ($effectiveDataTypes -contains "scorers" -or $effectiveDataTypes -contains "halftime") {
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
            Invoke-PythonModule -Label "detail_backfill_${competition}" -Module "app.pipelines.runner" -Arguments $arguments
        }
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
