[CmdletBinding()]
param(
    [string]$TargetDate,
    [switch]$DryRun,
    [switch]$UseDraft,
    [switch]$UseRewrite,
    [switch]$PublishX,
    [switch]$SkipPublishX,
    [switch]$PublishTypefully,
    [switch]$PublishBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\common.ps1"

Initialize-Runtime -LogName "cron_release.log" -SlotName "cron_release"

try {
    if ($PublishX.IsPresent -and $SkipPublishX.IsPresent) {
        throw "PublishX y SkipPublishX no se pueden usar a la vez."
    }

    $shouldPublishX = $PublishX.IsPresent -or (-not $SkipPublishX.IsPresent)
    Write-Log -Level "INFO" -Message "=== editorial_release.ps1 date=$TargetDate dry_run=$($DryRun.IsPresent) publish_x=$shouldPublishX publish_typefully=$($PublishTypefully.IsPresent) publish_browser=$($PublishBrowser.IsPresent) ==="

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
    if ($shouldPublishX) {
        $arguments += "--publish-x"
    }
    else {
        Write-Log -Level "INFO" -Message "Publicacion en X omitida por parametro."
    }
    if ($PublishTypefully.IsPresent) {
        $arguments += "--publish-typefully"
    }
    if ($PublishBrowser.IsPresent) {
        $arguments += "--publish-browser"
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
