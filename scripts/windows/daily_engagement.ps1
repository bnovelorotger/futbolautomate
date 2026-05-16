# Runs daily engagement (likes) via browser — simulates human activity
# Schedule: weekdays at 12:30 via Task Scheduler
param([switch]$DryRun)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "cron_engagement.log" -SlotName "cron_engagement"

try {
    $arguments = @("engage-daily")
    if ($DryRun.IsPresent) { $arguments += "--dry-run" }
    Invoke-PythonModule -Label "x_engagement" -Module "app.pipelines.x_publish" -Arguments $arguments
    Complete-Script
    exit 0
} catch {
    Fail-Script -ErrorRecord $_
    exit 1
} finally {
    Release-Lock
}
