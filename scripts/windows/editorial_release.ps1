[CmdletBinding()]
param(
    [string]$TargetDate,
    [switch]$DryRun,
    [switch]$UseDraft,
    [switch]$UseRewrite,
    [switch]$PublishX,
    [switch]$SkipPublishX,
    [switch]$PublishTypefully,
    [switch]$PublishBrowser,
    [switch]$SkipPublishBrowser,
    [int]$Limit = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "cron_release.log" -SlotName "cron_release"

try {
    $skipBrowserRequested = $SkipPublishBrowser.IsPresent -or $SkipPublishX.IsPresent
    $publishBrowserRequested = $PublishBrowser.IsPresent -or $PublishX.IsPresent

    if ($publishBrowserRequested -and $skipBrowserRequested) {
        throw "No se puede pedir y omitir a la vez la publicacion browser de X."
    }

    # Browser publishing es la unica via operativa real para X.
    # PublishX/SkipPublishX se mantienen como aliases legacy para no romper automatizaciones existentes.
    $shouldPublishX = $PublishX.IsPresent
    $shouldSkipBrowser = $skipBrowserRequested
    $shouldPublishBrowser = $publishBrowserRequested -or (-not $shouldSkipBrowser)

    Write-Log -Level "INFO" -Message "=== editorial_release.ps1 date=$TargetDate dry_run=$($DryRun.IsPresent) publish_x=$shouldPublishX skip_publish_x=$($SkipPublishX.IsPresent) publish_browser=$shouldPublishBrowser publish_typefully=$($PublishTypefully.IsPresent) ==="

    # --- PRE-FLIGHT: verificacion de sesion de browser ---
    # Solo advertimos; el export y el approval se ejecutan igualmente aunque la sesion este caducada.
    if ($shouldPublishBrowser) {
        $stateFile = Join-Path $script:ProjectRoot ".x_browser_state.json"
        if (-not (Test-Path -LiteralPath $stateFile)) {
            Write-Log -Level "WARN" -Message "PRE-FLIGHT: .x_browser_state.json no encontrado. La publicacion via browser fallara. Ejecuta: python -m app.pipelines.x_publish browser-auth-capture"
        }
        else {
            $fileAge = (Get-Date) - (Get-Item -LiteralPath $stateFile).LastWriteTime
            if ($fileAge.TotalDays -gt 7) {
                $ageDays = [int]$fileAge.TotalDays
                Write-Log -Level "WARN" -Message "PRE-FLIGHT: .x_browser_state.json tiene $ageDays dias de antiguedad (umbral: 7). La sesion puede estar proxima a caducar. Considera ejecutar: python -m app.pipelines.x_publish browser-auth-capture"
            }
            else {
                Write-Log -Level "INFO" -Message "PRE-FLIGHT: .x_browser_state.json presente y reciente ($([int]$fileAge.TotalDays) dias)."
            }
        }
    }
    # --- FIN PRE-FLIGHT ---

    $arguments = @()
    if ($DryRun.IsPresent) {
        $arguments += "dry-run"
    }
    else {
        $arguments += "run"
    }

    if ($TargetDate) {
        $arguments += @("--date", $TargetDate)
    }
    if ($Limit -gt 0) {
        $arguments += @("--limit", $Limit)
    }
    if ($UseDraft.IsPresent) {
        $arguments += "--use-draft"
    }
    elseif ($UseRewrite.IsPresent) {
        $arguments += "--use-rewrite"
    }
    if ($PublishTypefully.IsPresent) {
        $arguments += "--publish-typefully"
    }
    if ($shouldPublishBrowser) {
        if ($shouldPublishX) {
            Write-Log -Level "INFO" -Message "PublishX actua como alias legacy y delega en --publish-browser."
        }
        if ($PublishBrowser.IsPresent) {
            Write-Log -Level "INFO" -Message "PublishBrowser fuerza el backend browser canonico para X."
        }
        $arguments += "--publish-browser"
    }
    else {
        if ($SkipPublishX.IsPresent) {
            Write-Log -Level "INFO" -Message "SkipPublishX actua como alias legacy y delega en -SkipPublishBrowser."
        }
        Write-Log -Level "INFO" -Message "Publicacion via browser omitida por parametro."
    }

    Invoke-PythonModule -Label "editorial_release" -Module "app.pipelines.editorial_release" -Arguments $arguments

    Sync-DraftTempSnapshot
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
