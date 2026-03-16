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

Initialize-Runtime -LogName "cron_release.log" -SlotName "cron_release"

try {
    Write-Log -Level "INFO" -Message "=== editorial_release.ps1 date=$TargetDate dry_run=$($DryRun.IsPresent) ==="

    $arguments = @()
    if ($DryRun.IsPresent) {
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

    Invoke-PythonModule -Label "editorial_release" -Module "app.pipelines.editorial_release" -Arguments $arguments

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
