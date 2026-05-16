[CmdletBinding()]
param(
    [int]$Limit = 20,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "cron_publish_browser.log" -SlotName "cron_publish_browser"

try {
    Write-Log -Level "INFO" -Message "=== auto_publish_browser.ps1 limit=$Limit dry_run=$($DryRun.IsPresent) mode=browser_canonical ==="

    $arguments = @("browser-pending", "--limit", $Limit)
    if ($DryRun.IsPresent) {
        $arguments += "--dry-run"
    }

    Invoke-PythonModule -Label "x_publish" -Module "app.pipelines.x_publish" -Arguments $arguments

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
