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
    [switch]$SkipPublishBrowser
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
