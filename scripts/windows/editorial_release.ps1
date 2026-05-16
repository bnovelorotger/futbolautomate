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
    if ($PublishX.IsPresent -and $SkipPublishX.IsPresent) {
        throw "PublishX y SkipPublishX no se pueden usar a la vez."
    }
    if ($PublishBrowser.IsPresent -and $SkipPublishBrowser.IsPresent) {
        throw "PublishBrowser y SkipPublishBrowser no se pueden usar a la vez."
    }

    # Browser publishing es la unica via operativa real para X.
    # PublishX se mantiene como alias legacy para no romper automatizaciones existentes.
    $shouldPublishX = $PublishX.IsPresent
    $shouldPublishBrowser = $PublishX.IsPresent -or $PublishBrowser.IsPresent -or (-not $SkipPublishBrowser.IsPresent)

    Write-Log -Level "INFO" -Message "=== editorial_release.ps1 date=$TargetDate dry_run=$($DryRun.IsPresent) publish_x=$shouldPublishX publish_browser=$shouldPublishBrowser publish_typefully=$($PublishTypefully.IsPresent) ==="

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
        $arguments += "--publish-browser"
    }
    else {
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
