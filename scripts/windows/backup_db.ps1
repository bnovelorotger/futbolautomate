[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "cron_backup_db.log" -SlotName "cron_backup_db"

try {
    Write-Log -Level "INFO" -Message "=== backup_db.ps1 ==="

    # Read DATABASE_URL from environment (loaded by Initialize-Runtime via Import-EnvFile)
    $databaseUrl = $env:DATABASE_URL
    if ([string]::IsNullOrWhiteSpace($databaseUrl)) {
        throw "DATABASE_URL no esta definida en el archivo .env."
    }

    # Strip the SQLAlchemy driver prefix so pg_dump can parse the URL.
    # Expected format: postgresql+psycopg://user:password@host:port/dbname
    $plainUrl = $databaseUrl -replace '^postgresql\+[^:]+://', 'postgresql://'

    # Parse credentials and connection parameters from the URL.
    # postgresql://user:password@host:port/dbname
    if ($plainUrl -notmatch '^postgresql://([^:]+):([^@]+)@([^:/]+):(\d+)/(.+)$') {
        throw "No se puede parsear DATABASE_URL. Formato esperado: postgresql+psycopg://user:password@host:port/dbname"
    }

    $dbUser   = $Matches[1]
    $dbPass   = $Matches[2]
    $dbHost   = $Matches[3]
    $dbPort   = $Matches[4]
    $dbName   = $Matches[5]

    # Ensure the backups directory exists at the project root.
    $backupsDir = Join-Path $script:ProjectRoot "backups"
    New-Item -ItemType Directory -Force -Path $backupsDir | Out-Null

    # Build the timestamped filename.
    $timestamp   = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile  = Join-Path $backupsDir "backup_${timestamp}.dump"

    Write-Log -Level "INFO" -Message "Iniciando pg_dump -> $backupFile"

    # Set PGPASSWORD to avoid interactive password prompt.
    $env:PGPASSWORD = $dbPass

    try {
        $pgOutput = & pg_dump `
            --host=$dbHost `
            --port=$dbPort `
            --username=$dbUser `
            --format=custom `
            --file=$backupFile `
            $dbName 2>&1

        $pgExitCode = $LASTEXITCODE
    }
    finally {
        # Always clear the password from the environment.
        Remove-Item -Path "Env:PGPASSWORD" -ErrorAction SilentlyContinue
    }

    if ($pgExitCode -ne 0) {
        $pgMessage = ($pgOutput | ForEach-Object { $_.ToString() }) -join " "
        throw "pg_dump fallo (exit=$pgExitCode): $pgMessage"
    }

    # Log success with file size.
    $backupItem = Get-Item -LiteralPath $backupFile
    $sizeMB = [math]::Round($backupItem.Length / 1MB, 2)
    Write-Log -Level "INFO" -Message "Backup completado: $(Split-Path $backupFile -Leaf) ($sizeMB MB)"

    # Rotate old backups: delete .dump files older than 7 days.
    $cutoff    = (Get-Date).AddDays(-7)
    $oldDumps  = Get-ChildItem -LiteralPath $backupsDir -Filter "*.dump" |
                    Where-Object { $_.LastWriteTime -lt $cutoff }

    foreach ($old in $oldDumps) {
        Remove-Item -LiteralPath $old.FullName -Force
        Write-Log -Level "INFO" -Message "Backup antiguo eliminado: $($old.Name)"
    }

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
