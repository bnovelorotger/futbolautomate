# Digest editorial diario para consola y envio opcional a Telegram.
# Schedule sugerido: diario tras el cierre operativo editorial.
param(
    [string]$Date,
    [int]$Days = 1,
    [switch]$SendTelegram,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "editorial_daily_digest.log" -SlotName "editorial_daily_digest"

try {
    Write-Log -Level "INFO" -Message "=== editorial_daily_digest.ps1 ==="

    $arguments = @("--days", $Days.ToString())
    if (-not [string]::IsNullOrWhiteSpace($Date)) {
        $arguments += @("--date", $Date)
    }
    if ($SendTelegram.IsPresent) {
        $arguments += "--send-telegram"
    }
    if ($DryRun.IsPresent) {
        $arguments += "--dry-run"
        Write-Log -Level "INFO" -Message "Modo dry-run: se genera preview sin envios externos."
    }

    $output = & $script:PythonBin -m app.pipelines.runner editorial_daily_digest @arguments 2>&1
    $exitCode = $LASTEXITCODE

    foreach ($line in ($output | ForEach-Object { $_.ToString() })) {
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            Write-Log -Level "INFO" -Message $line
        }
    }

    if ($exitCode -ne 0) {
        throw "editorial_daily_digest fallo (exit=$exitCode)."
    }

    Complete-Script
    exit 0
} catch {
    Fail-Script -ErrorRecord $_
    exit 1
} finally {
    Release-Lock
}
