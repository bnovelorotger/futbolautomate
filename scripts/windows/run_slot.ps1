Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $args -or $args.Count -lt 1) {
    Write-Error "Uso: run_slot.ps1 <refresh|readiness|editorial-day|editorial-release|autoexport> [YYYY-MM-DD] [-PreviewOnly] [-DryRun] [-UseDraft] [-UseRewrite] [-RefreshSource futbolme]"
    exit 2
}

$slotName = [string]$args[0]
$targetDate = $null
$previewOnly = $false
$dryRun = $false
$useDraft = $false
$useRewrite = $false
$refreshSource = "futbolme"

for ($index = 1; $index -lt $args.Count; $index++) {
    switch ([string]$args[$index]) {
        "-PreviewOnly" {
            $previewOnly = $true
            continue
        }
        "-DryRun" {
            $dryRun = $true
            continue
        }
        "-UseDraft" {
            $useDraft = $true
            continue
        }
        "-UseRewrite" {
            $useRewrite = $true
            continue
        }
        "-RefreshSource" {
            $index++
            if ($index -ge $args.Count) {
                Write-Error "Falta valor para -RefreshSource"
                exit 2
            }
            $refreshSource = [string]$args[$index]
            continue
        }
        default {
            if (-not $targetDate) {
                $targetDate = [string]$args[$index]
                continue
            }
            Write-Error "Argumento no soportado: $($args[$index])"
            exit 2
        }
    }
}

switch ($slotName) {
    "refresh" {
        & "$PSScriptRoot\refresh_data.ps1" -RefreshSource $refreshSource
        exit $LASTEXITCODE
    }
    "readiness" {
        & "$PSScriptRoot\readiness_check.ps1"
        exit $LASTEXITCODE
    }
    "editorial-day" {
        if ($targetDate) {
            & "$PSScriptRoot\run_editorial_day.ps1" -TargetDate $targetDate -PreviewOnly:$previewOnly
        }
        else {
            & "$PSScriptRoot\run_editorial_day.ps1" -PreviewOnly:$previewOnly
        }
        exit $LASTEXITCODE
    }
    "editorial-release" {
        if ($targetDate) {
            & "$PSScriptRoot\editorial_release.ps1" -TargetDate $targetDate -DryRun:$dryRun -UseDraft:$useDraft -UseRewrite:$useRewrite
        }
        else {
            & "$PSScriptRoot\editorial_release.ps1" -DryRun:$dryRun -UseDraft:$useDraft -UseRewrite:$useRewrite
        }
        exit $LASTEXITCODE
    }
    "autoexport" {
        if ($targetDate) {
            & "$PSScriptRoot\typefully_autoexport.ps1" -TargetDate $targetDate -DryRun:$dryRun -UseDraft:$useDraft -UseRewrite:$useRewrite
        }
        else {
            & "$PSScriptRoot\typefully_autoexport.ps1" -DryRun:$dryRun -UseDraft:$useDraft -UseRewrite:$useRewrite
        }
        exit $LASTEXITCODE
    }
    default {
        Write-Error "Slot no soportado: $slotName"
        exit 2
    }
}
