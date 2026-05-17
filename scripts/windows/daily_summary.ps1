# Resumen operativo diario del pipeline editorial
# Ejecuta pipeline_summary con ventana de 1 dia y loggea el resultado.
# Si hay alertas activas (exit code 1), loggea a nivel ERROR.
# Schedule: diario a las 21:00 via Task Scheduler.
param(
    [string]$Date,
    [int]$Days = 1,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "cron_summary.log" -SlotName "cron_summary"

try {
    Write-Log -Level "INFO" -Message "=== daily_summary.ps1 ==="

    $arguments = @("--days", $Days.ToString())
    if (-not [string]::IsNullOrWhiteSpace($Date)) {
        $arguments += @("--date", $Date)
    }
    if ($DryRun.IsPresent) {
        Write-Log -Level "INFO" -Message "Modo dry-run: pipeline_summary solo consulta, no modifica nada."
    }

    # Capturar output y exit code por separado para poder loggear segun nivel
    $output = & $script:PythonBin -m app.pipelines.runner pipeline_summary @arguments 2>&1
    $exitCode = $LASTEXITCODE

    $outputText = ($output | ForEach-Object { $_.ToString() }) -join "`n"

    if ($exitCode -eq 0) {
        Write-Log -Level "INFO" -Message "pipeline_summary completado sin alertas."
        foreach ($line in ($output | ForEach-Object { $_.ToString() })) {
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Write-Log -Level "INFO" -Message $line
            }
        }
    } else {
        Write-Log -Level "ERROR" -Message "pipeline_summary reporta alertas activas (exit=$exitCode)."
        foreach ($line in ($output | ForEach-Object { $_.ToString() })) {
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Write-Log -Level "ERROR" -Message $line
            }
        }
    }

    Complete-Script
    # Propagar el exit code del summary: 0=ok, 1=alertas
    exit $exitCode
} catch {
    Fail-Script -ErrorRecord $_
    exit 1
} finally {
    Release-Lock
}
