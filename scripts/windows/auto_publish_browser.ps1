[CmdletBinding()]
param(
    [int]$Limit = 20,
    [switch]$DryRun,
    # Stagger entre tweets en segundos. Si no se especifica usa la configuracion de Settings.
    [int]$Stagger = -1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "cron_publish_browser.log" -SlotName "cron_publish_browser"

try {
    Write-Log -Level "INFO" -Message "=== auto_publish_browser.ps1 limit=$Limit dry_run=$($DryRun.IsPresent) stagger=$Stagger ==="

    # --- PASO 1: Verificar sesion antes de intentar publicar ---
    $stateFile = Join-Path $script:ProjectRoot ".x_browser_state.json"
    if (-not (Test-Path -LiteralPath $stateFile)) {
        Write-Log -Level "ERROR" -Message "Sesion de browser no encontrada ($stateFile). Para renovarla ejecuta: python -m app.pipelines.x_publish browser-auth-capture"
        Fail-Script -ErrorRecord ([System.Management.Automation.ErrorRecord]::new(
            [System.Exception]::new("Sesion de browser X inexistente. Renueva con: python -m app.pipelines.x_publish browser-auth-capture"),
            "SessionMissing",
            [System.Management.Automation.ErrorCategory]::ResourceUnavailable,
            $stateFile
        ))
        exit 1
    }

    # Verificacion ligera de sesion via runner (abre Chromium headless, comprueba /home sin /login)
    Write-Log -Level "INFO" -Message "Verificando sesion de browser X..."
    $sessionCheckOutput = & $script:PythonBin -m app.pipelines.runner x_browser_session_check 2>&1
    $sessionCheckExit = $LASTEXITCODE

    foreach ($line in $sessionCheckOutput) {
        $text = $line.ToString()
        if (-not [string]::IsNullOrWhiteSpace($text)) {
            Write-Log -Level "INFO" -Message "[session_check] $text"
        }
    }

    if ($sessionCheckExit -ne 0) {
        Write-Log -Level "ERROR" -Message "Sesion de browser X invalida o caducada. Para renovarla ejecuta: python -m app.pipelines.x_publish browser-auth-capture"
        # No lanzamos excepcion: la sesion invalida es un problema de configuracion, no un fallo del script.
        # Salimos con codigo 1 para que Task Scheduler lo registre como error pero sin stack trace innecesario.
        exit 1
    }

    Write-Log -Level "INFO" -Message "Sesion de browser X verificada correctamente."

    # --- PASO 2: Publicar piezas pendientes ---
    $arguments = @("browser-pending", "--limit", $Limit)
    if ($DryRun.IsPresent) {
        $arguments += "--dry-run"
    }
    if ($Stagger -ge 0) {
        $arguments += @("--stagger", $Stagger)
    }

    Invoke-PythonModule -Label "x_publish" -Module "app.pipelines.x_publish" -Arguments $arguments

    Complete-Script
    exit 0
}
catch {
    $msg = if ($_.Exception) { $_.Exception.Message } else { $_.ToString() }

    # Distinguish session errors from generic publish errors for actionable log messages.
    if ($msg -match "Session expired|sesion.*expirada|x_browser_auth|browser-auth-capture") {
        Write-Log -Level "ERROR" -Message "ERROR DE SESION X: $msg"
        Write-Log -Level "ERROR" -Message "Accion requerida: python -m app.pipelines.x_publish browser-auth-capture"
    }
    else {
        Fail-Script -ErrorRecord $_
    }
    exit 1
}
finally {
    Release-Lock
}
