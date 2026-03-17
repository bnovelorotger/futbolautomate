[CmdletBinding()]
param(
    [string]$TargetDate,
    [switch]$DryRun,
    [switch]$UseDraft,
    [switch]$UseRewrite
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

$effectiveDryRun = $DryRun.IsPresent -or (Test-Truthy -Value $env:AUTOEXPORT_DRY_RUN)

Initialize-Runtime -LogName "cron_autoexport.log" -SlotName "cron_autoexport"

try {
    Write-Log -Level "INFO" -Message "=== typefully_autoexport.ps1 date=$TargetDate dry_run=$effectiveDryRun ==="

    $arguments = @()
    if ($effectiveDryRun) {
        $arguments += "dry-run"
    }
    else {
        $arguments += "run"
    }

    if ($TargetDate) {
        $arguments += @("--date", $TargetDate)
    }
    if ($UseDraft.IsPresent) {
        $arguments += "--use-draft"
    }
    elseif ($UseRewrite.IsPresent) {
        $arguments += "--use-rewrite"
    }

    Invoke-PythonModule -Label "typefully_autoexport" -Module "app.pipelines.typefully_autoexport" -Arguments $arguments

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
