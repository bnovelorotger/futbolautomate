# Ejecutar como Administrador: clic derecho -> "Ejecutar con PowerShell" (como admin)
# Crea las 5 tareas programadas del pipeline de futbolalear

$project = "C:\Users\bnove\Documents\futbolbalear"
$ps = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$user = $env:USERNAME
$allDays = @("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")

function Register-FutbolTask {
    param($Name, $Script, $TimeStr)
    $action = New-ScheduledTaskAction `
        -Execute $ps `
        -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$project\$Script`"" `
        -WorkingDirectory $project
    $triggers = $allDays | ForEach-Object {
        New-ScheduledTaskTrigger -Weekly -DaysOfWeek $_ -At $TimeStr
    }
    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable:$false `
        -WakeToRun:$false
    $principal = New-ScheduledTaskPrincipal `
        -UserId $user `
        -LogonType Interactive `
        -RunLevel Highest
    if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    }
    Register-ScheduledTask `
        -TaskName $Name `
        -Action $action `
        -Trigger $triggers `
        -Settings $settings `
        -Principal $principal `
        -Force | Out-Null
    Write-Host "[OK] $Name -> $TimeStr"
}

Write-Host "Registrando tareas del pipeline futbolbalear..."
Write-Host ""

# 1. Scraping de datos — dos veces al dia
Register-FutbolTask "futbol_refresh_morning"   "scripts\windows\refresh_data.ps1"     "07:00"
Register-FutbolTask "futbol_refresh_afternoon" "scripts\windows\refresh_data.ps1"     "14:00"

# 2. Generacion de contenido editorial
Register-FutbolTask "futbol_editorial_day"     "scripts\windows\run_editorial_day.ps1" "09:00"

# 3. Release + publicacion via browser (--publish-browser activado por defecto)
Register-FutbolTask "futbol_release"           "scripts\windows\editorial_release.ps1" "10:30"

# 4. Backup de base de datos
Register-FutbolTask "futbol_backup"            "scripts\windows\backup_db.ps1"         "03:00"

Write-Host ""
Write-Host "=== Tareas registradas ==="
Get-ScheduledTask | Where-Object { $_.TaskName -like "futbol_*" } | `
    Select-Object TaskName, State | Format-Table -AutoSize

Write-Host "Listo. El pipeline se ejecutara automaticamente cada dia."
Write-Host "Recuerda: el ordenador debe estar encendido a las horas programadas."
