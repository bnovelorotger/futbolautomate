[CmdletBinding()]
param(
    [int]$Limit = 50,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "auto_publish_typefully.log" -SlotName "auto_publish_typefully"

try {
    Write-Log -Level "INFO" -Message "=== auto_publish_typefully.ps1 limit=$Limit dry_run=$($DryRun.IsPresent) ==="

    # Runs Typefully publish-pending independently
    # Schedule via Task Scheduler after editorial_release completes
    $arguments = @("typefully-pending", "--limit", "$Limit")
    if ($DryRun.IsPresent) {
        $arguments += "--dry-run"
    }

    Invoke-PythonModule -Label "typefully_pending" -Module "app.pipelines.x_publish" -Arguments $arguments

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
