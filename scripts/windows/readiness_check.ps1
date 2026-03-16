[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "cron_readiness.log" -SlotName "cron_readiness"

try {
    Write-Log -Level "INFO" -Message "=== readiness_check.ps1 ==="
    Invoke-PythonModule -Label "competition_catalog_status" -Module "app.pipelines.competition_catalog" -Arguments @(
        "status",
        "--integrated-only"
    )
    Invoke-PythonModule -Label "editorial_readiness" -Module "app.pipelines.system_check" -Arguments @(
        "editorial-readiness"
    )

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
