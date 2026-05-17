# Agenda editorial de la jornada para consola y envio opcional a Telegram.
# Schedule sugerido: diario a las 09:00.
param(
    [string]$Date,
    [switch]$SendTelegram,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "editorial_day_plan.log" -SlotName "editorial_day_plan"

try {
    Write-Log -Level "INFO" -Message "=== editorial_day_plan.ps1 ==="

    $arguments = @()
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

    $output = & $script:PythonBin -m app.pipelines.runner editorial_day_plan @arguments 2>&1
    $exitCode = $LASTEXITCODE

    foreach ($line in ($output | ForEach-Object { $_.ToString() })) {
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            Write-Log -Level "INFO" -Message $line
        }
    }

    if ($exitCode -ne 0) {
        throw "editorial_day_plan fallo (exit=$exitCode)."
    }

    Complete-Script
    exit 0
} catch {
    Fail-Script -ErrorRecord $_
    exit 1
} finally {
    Release-Lock
}

