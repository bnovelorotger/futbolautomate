[CmdletBinding()]
param(
    [int]$Limit = 20,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "auto_publish.log" -SlotName "auto_publish"

try {
    Write-Log -Level "INFO" -Message "=== auto_publish.ps1 limit=$Limit dry_run=$($DryRun.IsPresent) ==="

    $arguments = @("publish-pending", "--limit", "$Limit")
    if ($DryRun.IsPresent) {
        $arguments += "--dry-run"
    }

    Invoke-PythonModule -Label "x_publish_pending" -Module "app.pipelines.x_publish" -Arguments $arguments

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
