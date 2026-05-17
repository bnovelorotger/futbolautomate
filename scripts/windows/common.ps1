Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

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


function Invoke-LogRotation {
    param(
        [string]$LogFile,
        [int]$MaxSizeBytes = 5242880,
        [int]$KeepRotated = 3
    )

    try {
        if (-not (Test-Path -LiteralPath $LogFile)) {
            return
        }

        $fileInfo = Get-Item -LiteralPath $LogFile
        if ($fileInfo.Length -le $MaxSizeBytes) {
            return
        }

        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $bakFile = "${LogFile}.${timestamp}.bak"
        Rename-Item -LiteralPath $LogFile -NewName $bakFile

        $dir = Split-Path -LiteralPath $LogFile -Parent
        $base = Split-Path -LiteralPath $LogFile -Leaf
        $existing = Get-ChildItem -LiteralPath $dir -Filter "${base}.*.bak" |
            Sort-Object LastWriteTime -Descending
        if ($existing.Count -gt $KeepRotated) {
            $existing | Select-Object -Skip $KeepRotated | Remove-Item -Force
        }
    }
    catch {
        # Rotation failure must never block the calling script
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
    Invoke-LogRotation -LogFile $script:CurrentLogFile

    # Clean up stale locks before attempting to acquire our own slot.
    Remove-StaleLocks
    Acquire-Lock -SlotName $SlotName
}


function Remove-StaleLocks {
    # Lock files older than 2 hours indicate a zombie process (e.g. suspended while Playwright was open).
    # We remove them before acquiring the current slot so the new run is not blocked by a ghost lock.
    param(
        [int]$MaxAgeHours = 2
    )

    $staleFiles = Get-ChildItem -LiteralPath $script:LockDir -Filter "*.lock" -File -ErrorAction SilentlyContinue |
        Where-Object { ((Get-Date) - $_.LastWriteTime).TotalHours -gt $MaxAgeHours }

    foreach ($lockFile in $staleFiles) {
        try {
            # Try to open exclusively; if we can, the file is not held by anyone — safe to delete.
            $stream = [System.IO.File]::Open(
                $lockFile.FullName,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::None
            )
            $stream.Dispose()
            Remove-Item -LiteralPath $lockFile.FullName -Force -ErrorAction SilentlyContinue
            Write-Log -Level "WARN" -Message "Lock colgado eliminado: $($lockFile.Name) (edad: $([int]((Get-Date) - $lockFile.LastWriteTime).TotalHours)h)"
        }
        catch {
            # File is still held by another process — leave it alone.
            Write-Log -Level "WARN" -Message "Lock antiguo detectado pero sigue bloqueado por otro proceso: $($lockFile.Name)"
        }
    }
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


function Sync-DraftTempSnapshot {
    try {
        Invoke-PythonModule -Label "draft_temp_sync" -Module "app.pipelines.draft_temp" -Arguments @("sync")
    }
    catch {
        $message = if ($_.Exception) {
            $_.Exception.Message
        }
        else {
            $_.ToString()
        }
        Write-Log -Level "WARN" -Message "No se pudo actualizar draft_temp.json: $message"
    }
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
