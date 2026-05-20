# Ejecutar como Administrador: clic derecho -> "Ejecutar con PowerShell" (como admin)
# Crea las tareas programadas del pipeline de futbolbalear con horarios optimos por dia.

$project = "C:\Users\bnove\Documents\futbolbalear"
$ps = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$user = $env:USERNAME

function Register-FutbolTask {
    param(
        $Name,
        $Script,
        $TimeStr,
        [string[]]$Days,
        [string]$ScriptArguments = "",
        [int]$ExecutionHours = 1
    )
    $fullArgument = "-NonInteractive -ExecutionPolicy Bypass -File `"$project\$Script`""
    if (-not [string]::IsNullOrWhiteSpace($ScriptArguments)) {
        $fullArgument = "$fullArgument $ScriptArguments"
    }
    $action = New-ScheduledTaskAction `
        -Execute $ps `
        -Argument $fullArgument `
        -WorkingDirectory $project
    $triggers = $Days | ForEach-Object {
        New-ScheduledTaskTrigger -Weekly -DaysOfWeek $_ -At $TimeStr
    }
    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours $ExecutionHours) `
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
    Write-Host "[OK] $Name -> $Days @ $TimeStr"
}

function Unregister-FutbolTaskIfExists {
    param($Name)
    if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Host "[OK] $Name -> tarea legacy eliminada"
    }
}

Write-Host "Registrando tareas del pipeline futbolbalear..."
Write-Host ""

@(
    "futbol_editorial_day_mon_sun",
    "futbol_release_mon_sun",
    "futbol_release_other"
) | ForEach-Object { Unregister-FutbolTaskIfExists $_ }

# Legacy "uFutbolBalear *" tasks from the previous task naming convention.
# These shadow the futbol_* tasks and trigger duplicate runs of the same
# scripts (refresh/editorial day/release/readiness) on Mon/Wed/Fri/Sun.
Get-ScheduledTask -ErrorAction SilentlyContinue |
    Where-Object { $_.TaskName -like "uFutbolBalear*" } |
    ForEach-Object {
        Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false
        Write-Host "[OK] $($_.TaskName) -> tarea legacy uFutbolBalear eliminada"
    }

Write-Host ""

# --- Scraping de datos ---
# Lunes/domingo: scraping temprano para tener datos de resultados del fin de semana.
Register-FutbolTask "futbol_refresh_morning"   "scripts\windows\refresh_data.ps1" "06:30" @("Monday","Sunday")
# Miercoles/viernes: scraping antes de generacion de contenido.
Register-FutbolTask "futbol_refresh_midweek"   "scripts\windows\refresh_data.ps1" "07:00" @("Wednesday","Friday")
# Resto de dias: scraping matutino estandar.
Register-FutbolTask "futbol_refresh_other"     "scripts\windows\refresh_data.ps1" "07:00" @("Tuesday","Thursday","Saturday")
# Scraping vespertino diario.
Register-FutbolTask "futbol_refresh_afternoon" "scripts\windows\refresh_data.ps1" "14:00" @("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")
# Domingo: refresco extra antes del cierre nocturno.
Register-FutbolTask "futbol_refresh_sunday_evening" "scripts\windows\refresh_data.ps1" "20:00" @("Sunday")

# --- Generacion de contenido editorial ---
# Lunes: resultados + clasificaciones post fin de semana antes del primer slot fuerte.
Register-FutbolTask "futbol_editorial_day_mon" "scripts\windows\run_editorial_day.ps1" "07:30" @("Monday")
# Martes/jueves/sabado: capa ligera de continuidad editorial.
Register-FutbolTask "futbol_editorial_day_other" "scripts\windows\run_editorial_day.ps1" "18:30" @("Tuesday","Thursday")
# Sabado: previa ligera en la manana.
Register-FutbolTask "futbol_editorial_day_sat" "scripts\windows\run_editorial_day.ps1" "09:30" @("Saturday")
# Miercoles: historias y metricas para prime time de noche.
Register-FutbolTask "futbol_editorial_day_wed" "scripts\windows\run_editorial_day.ps1" "18:30" @("Wednesday")
# Viernes: previews antes de la ventana de comida.
Register-FutbolTask "futbol_editorial_day_fri" "scripts\windows\run_editorial_day.ps1" "08:00" @("Friday")
# Domingo: resultados recientes del tramo final de la jornada.
Register-FutbolTask "futbol_editorial_day_sun" "scripts\windows\run_editorial_day.ps1" "20:45" @("Sunday")

# --- Release + publicacion ---
# Lunes: primer slot de alta atencion post fin de semana, con 4 posts maximo.
Register-FutbolTask "futbol_release_mon" "scripts\windows\editorial_release.ps1" "09:15" @("Monday") "-Limit 4" 3
# Martes/jueves: continuidad de noche con menor volumen.
Register-FutbolTask "futbol_release_other" "scripts\windows\editorial_release.ps1" "20:00" @("Tuesday","Thursday") "-Limit 3" 2
# Miercoles: prime time de noche para piezas conversacionales.
Register-FutbolTask "futbol_release_wed" "scripts\windows\editorial_release.ps1" "20:00" @("Wednesday") "-Limit 4" 3
# Viernes: ventana de comida para previas del fin de semana.
Register-FutbolTask "futbol_release_fri" "scripts\windows\editorial_release.ps1" "13:00" @("Friday") "-Limit 4" 3
# Sabado: previa ligera del dia.
Register-FutbolTask "futbol_release_sat" "scripts\windows\editorial_release.ps1" "11:00" @("Saturday") "-Limit 2" 2
# Domingo: cierre ligero, sin invadir el digest de las 22:00.
Register-FutbolTask "futbol_release_sun" "scripts\windows\editorial_release.ps1" "21:15" @("Sunday") "-Limit 2" 2

# --- Agenda Telegram de la jornada ---
Register-FutbolTask "futbol_editorial_day_plan" "scripts\windows\editorial_day_plan.ps1" "08:00" @("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday") "-SendTelegram"

# --- Resumen operativo diario ---
Register-FutbolTask "futbol_summary"          "scripts\windows\daily_summary.ps1"          "21:00" @("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")
Register-FutbolTask "futbol_editorial_digest" "scripts\windows\editorial_daily_digest.ps1" "22:00" @("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday") "-SendTelegram"

# --- Engagement diario (like a tweets del timeline) ---
Register-FutbolTask "futbol_engagement" "scripts\windows\daily_engagement.ps1" "12:30" @("Monday","Tuesday","Wednesday","Thursday","Friday")

# --- Verificacion de sesion de X browser ---
# Lunes a las 06:00: antes del scraping (06:30) y del editorial (07:30) para alertar a tiempo.
Register-FutbolTask "futbol_session_check" "scripts\windows\check_browser_session.ps1" "06:00" @("Monday")

# --- Backup de base de datos ---
Register-FutbolTask "futbol_backup" "scripts\windows\backup_db.ps1" "03:00" @("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")

# --- Limpieza semanal de logs ---
Register-FutbolTask "futbol_log_cleanup" "scripts\windows\cleanup_logs.ps1" "04:00" @("Sunday")

Write-Host ""
Write-Host "=== Tareas registradas ==="
Get-ScheduledTask | Where-Object { $_.TaskName -like "futbol_*" } |
    Select-Object TaskName, State | Format-Table -AutoSize

Write-Host "Listo. El pipeline se ejecutara automaticamente segun el horario optimo por dia."
Write-Host "Recuerda: el ordenador debe estar encendido a las horas programadas."
