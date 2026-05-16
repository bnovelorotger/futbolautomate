[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "cron_cleanup.log" -SlotName "cron_cleanup"

try {
    Write-Log -Level "INFO" -Message "=== cleanup_logs.ps1 ==="

    $cutoff = (Get-Date).AddDays(-30)
    $logsDir = Join-Path $script:ProjectRoot "logs"
    $stale = Get-ChildItem -LiteralPath $logsDir -Filter "*.bak" |
        Where-Object { $_.LastWriteTime -lt $cutoff }

    $count = 0
    foreach ($file in $stale) {
        Remove-Item -LiteralPath $file.FullName -Force
        $count++
    }

    Write-Log -Level "INFO" -Message "Archivos .bak eliminados: $count"

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
