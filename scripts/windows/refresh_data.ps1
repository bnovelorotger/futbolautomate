[CmdletBinding()]
param(
    [string]$RefreshSource = "futbolme"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

$competitions = @(
    "tercera_rfef_g11",
    "segunda_rfef_g3_baleares",
    "division_honor_mallorca",
    "tercera_federacion_femenina_g11",
    "primera_rfef_baleares",
    "division_honor_ibiza_form",
    "division_honor_menorca"
)
$targets = @("matches", "standings")

Initialize-Runtime -LogName "cron_refresh.log" -SlotName "cron_refresh"

try {
    Write-Log -Level "INFO" -Message "=== refresh_data.ps1 ==="
    Invoke-PythonModule -Label "seed_competitions_integrated" -Module "app.pipelines.competition_catalog" -Arguments @(
        "seed",
        "--integrated-only",
        "--missing-only"
    )

    foreach ($competition in $competitions) {
        foreach ($target in $targets) {
            Invoke-PythonModule -Label "refresh_${competition}_${target}" -Module "app.pipelines.run_source" -Arguments @(
                "--source", $RefreshSource,
                "--competition", $competition,
                "--target", $target
            )
        }
    }

    Sync-DraftTempSnapshot
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
