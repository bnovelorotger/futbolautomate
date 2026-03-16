Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:ProjectRoot = $null
$script:LogDir = $null
$script:LockDir = $null
$script:CurrentLogFile = $null
$script:PythonBin = $null
$script:LockStream = $null


function Import-EnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if (-not $line) {
            continue
        }
        if ($line.StartsWith("#")) {
            continue
        }
        if (-not $line.Contains("=")) {
            continue
        }

        $parts = $line -split "=", 2
        $key = $parts[0].Trim()
        $value = $parts[1]

        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        Set-Item -Path "Env:$key" -Value $value
    }
}


function Resolve-PythonBinary {
    if ($env:PYTHON_BIN -and (Test-Path -LiteralPath $env:PYTHON_BIN)) {
        return (Resolve-Path -LiteralPath $env:PYTHON_BIN).Path
    }

    $venvPython = Join-Path $script:ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return (Resolve-Path -LiteralPath $venvPython).Path
    }

    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return $pythonCommand.Source
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return $pythonCommand.Source
    }

    throw "No se encuentra Python. Define PYTHON_BIN o crea .venv\Scripts\python.exe."
}


function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Level,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Message
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
    $line = "[$timestamp] [$Level] $Message"

    if ($script:CurrentLogFile) {
        Add-Content -LiteralPath $script:CurrentLogFile -Value $line -Encoding UTF8
    }
    Write-Host $line
}


function Acquire-Lock {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SlotName
    )

    $lockFile = Join-Path $script:LockDir "$SlotName.lock"
    try {
        $script:LockStream = [System.IO.File]::Open(
            $lockFile,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    }
    catch {
        throw "Otra ejecucion sigue activa para $SlotName."
    }
}


function Release-Lock {
    if ($script:LockStream) {
        $script:LockStream.Dispose()
        $script:LockStream = $null
    }
}


function Initialize-Runtime {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LogName,
        [Parameter(Mandatory = $true)]
        [string]$SlotName
    )

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
    $script:CurrentLogFile = Join-Path $script:LogDir $LogName
    Acquire-Lock -SlotName $SlotName
}


function Invoke-PythonModule {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [string]$Module,
        [string[]]$Arguments = @()
    )

    Write-Log -Level "INFO" -Message "Inicio: $Label"
    $output = & $script:PythonBin -m $Module @Arguments 2>&1
    $exitCode = $LASTEXITCODE

    foreach ($line in $output) {
        $text = $line.ToString()
        if ([string]::IsNullOrWhiteSpace($text)) {
            continue
        }
        Write-Log -Level "INFO" -Message $text
    }

    if ($exitCode -ne 0) {
        throw "Comando fallido: python -m $Module $($Arguments -join ' ') (exit=$exitCode)"
    }

    Write-Log -Level "INFO" -Message "Fin: $Label"
}


function Test-Truthy {
    param(
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }

    return @("1", "true", "yes", "on") -contains $Value.Trim().ToLowerInvariant()
}


function Complete-Script {
    Write-Log -Level "INFO" -Message "Script completado"
}


function Fail-Script {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ErrorRecord
    )

    $message = if ($ErrorRecord.Exception) {
        $ErrorRecord.Exception.Message
    }
    else {
        $ErrorRecord.ToString()
    }

    Write-Log -Level "ERROR" -Message $message
}
