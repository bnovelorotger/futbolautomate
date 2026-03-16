[CmdletBinding()]
param(
    [string]$TargetDate,
    [switch]$PreviewOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

if (-not $TargetDate) {
    $TargetDate = Get-Date -Format "yyyy-MM-dd"
}

$previewMode = $PreviewOnly.IsPresent -or (Test-Truthy -Value $env:PREVIEW_ONLY)

Initialize-Runtime -LogName "cron_editorial.log" -SlotName "cron_editorial"

try {
    Write-Log -Level "INFO" -Message "=== run_editorial_day.ps1 date=$TargetDate preview_only=$previewMode ==="
    Invoke-PythonModule -Label "preview_day_$TargetDate" -Module "app.pipelines.editorial_ops" -Arguments @(
        "preview-day",
        "--date", $TargetDate
    )

    if ($previewMode) {
        Write-Log -Level "WARN" -Message "PREVIEW_ONLY=true: se omite run-daily"
        Complete-Script
        exit 0
    }

    Invoke-PythonModule -Label "run_editorial_day_$TargetDate" -Module "app.pipelines.editorial_ops" -Arguments @(
        "run-daily",
        "--date", $TargetDate
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
