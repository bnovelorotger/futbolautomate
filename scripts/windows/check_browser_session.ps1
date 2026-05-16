# Comprueba que la sesion de X Browser sigue activa antes de la ventana de publicacion
# Schedule: lunes a las 06:00 (30 min antes del scraping matutino)
# Sin lock: solo lectura, no modifica estado
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

# Inicializacion manual (sin lock — este script es de solo lectura)
$script:ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$script:LogDir = Join-Path $script:ProjectRoot "logs"
$script:LockDir = Join-Path $script:ProjectRoot ".locks"

New-Item -ItemType Directory -Force -Path $script:LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $script:LockDir | Out-Null

Set-Location -LiteralPath $script:ProjectRoot

Import-EnvFile -Path (Join-Path $script:ProjectRoot ".env")
Import-EnvFile -Path (Join-Path $script:ProjectRoot ".env.windows")

if (-not $env:APP_TIMEZONE) {
    $env:APP_TIMEZONE = "Europe/Madrid"
}

$script:PythonBin = Resolve-PythonBinary
$script:CurrentLogFile = Join-Path $script:LogDir "cron_session_check.log"

try {
    Write-Log -Level "INFO" -Message "=== check_browser_session.ps1 ==="

    $stateFile = Join-Path $script:ProjectRoot ".x_browser_state.json"
    if (-not (Test-Path -LiteralPath $stateFile)) {
        Write-Log -Level "WARN" -Message "Archivo de sesion .x_browser_state.json no encontrado"
        exit 1
    }

    Write-Log -Level "INFO" -Message "Verificando sesion de X browser con x_publish browser-auth-verify..."
    $output = & $script:PythonBin -m app.pipelines.x_publish browser-auth-verify 2>&1
    $exitCode = $LASTEXITCODE

    foreach ($line in $output) {
        $text = $line.ToString()
        if (-not [string]::IsNullOrWhiteSpace($text)) {
            Write-Log -Level "INFO" -Message $text
        }
    }

    if ($exitCode -eq 0) {
        Write-Log -Level "INFO" -Message "Sesion de X browser activa y valida"
        exit 0
    }
    else {
        Write-Log -Level "ERROR" -Message "ALERTA: Sesion de X browser caducada o invalida. Ejecutar: python -m app.pipelines.x_publish browser-auth-capture"
        exit 1
    }
}
catch {
    Fail-Script -ErrorRecord $_
    exit 1
}
