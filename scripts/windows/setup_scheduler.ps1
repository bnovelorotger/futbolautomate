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
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction Stop
    }
    Register-ScheduledTask `
        -TaskName $Name `
        -Action $action `
        -Trigger $triggers `
        -Settings $settings `
        -Principal $principal `
        -Force `
        -ErrorAction Stop | Out-Null
    Write-Host "[OK] $Name -> $Days @ $TimeStr"
}

function Unregister-FutbolTaskIfExists {
    param($Name)
    if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction Stop
        Write-Host "[OK] $Name -> tarea legacy eliminada"
    }
}

Write-Host "Registrando tareas del pipeline futbolbalear..."
Write-Host ""

@(
    "futbol_editorial_day_mon_sun",
    "futbol_release_mon_sun",
    "futbol_release_mon",
    "futbol_release_other",
    "futbol_release_wed",
    "futbol_release_fri",
    "futbol_publish_catchup_mon",
    "futbol_publish_catchup_tue",
    "futbol_publish_catchup_wed",
    "futbol_publish_catchup_thu",
    "futbol_publish_catchup_fri",
    "futbol_scorer_backfill_weekly"
) | ForEach-Object { Unregister-FutbolTaskIfExists $_ }

# Legacy "uFutbolBalear *" tasks from the previous task naming convention.
# These shadow the futbol_* tasks and trigger duplicate runs of the same
# scripts (refresh/editorial day/release/readiness) on Mon/Wed/Fri/Sun.
Get-ScheduledTask -ErrorAction SilentlyContinue |
    Where-Object { $_.TaskName -like "uFutbolBalear*" } |
    ForEach-Object {
        Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false -ErrorAction Stop
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
# Auditoria/backfill semanal de estadisticas. Mantiene la cobertura 2025-26 al dia
# sin competir con los slots editoriales ni con el refresco fuerte del domingo.
Register-FutbolTask "futbol_stats_backfill_weekly" "scripts\windows\backfill_stats.ps1" "05:00" @("Tuesday") "-Season 2025-26 -DataTypes results,standings,scorers,halftime -LimitPerCompetition 250 -IncludeErrors" 4

# --- Generacion de contenido editorial ---
# Lunes: resultados + clasificaciones post fin de semana antes del primer slot fuerte.
Register-FutbolTask "futbol_editorial_day_mon" "scripts\windows\run_editorial_day.ps1" "07:30" @("Monday")
# Martes/jueves: capa ligera de continuidad editorial antes del primer slot.
Register-FutbolTask "futbol_editorial_day_other" "scripts\windows\run_editorial_day.ps1" "08:30" @("Tuesday","Thursday")
# Sabado: previa ligera en la manana.
Register-FutbolTask "futbol_editorial_day_sat" "scripts\windows\run_editorial_day.ps1" "09:30" @("Saturday")
# Miercoles: historias y metricas antes del primer slot.
Register-FutbolTask "futbol_editorial_day_wed" "scripts\windows\run_editorial_day.ps1" "08:30" @("Wednesday")
# Viernes: previews antes del primer slot del dia.
Register-FutbolTask "futbol_editorial_day_fri" "scripts\windows\run_editorial_day.ps1" "08:00" @("Friday")
# Domingo: resultados recientes del tramo final de la jornada.
Register-FutbolTask "futbol_editorial_day_sun" "scripts\windows\run_editorial_day.ps1" "20:45" @("Sunday")

# --- Release + publicacion ---
# El cap es POR PUBLICACION via browser, NO por evaluacion. De lunes a viernes
# hay dos slots diarios de bajo volumen para repartir la salida entre manana y noche.
Register-FutbolTask "futbol_release_weekday_morning" "scripts\windows\editorial_release.ps1" "09:30" @("Monday","Tuesday","Wednesday","Thursday","Friday") "-PublishLimit 2" 2
Register-FutbolTask "futbol_release_weekday_evening" "scripts\windows\editorial_release.ps1" "19:30" @("Monday","Tuesday","Wednesday","Thursday","Friday") "-PublishLimit 2" 2
# Sabado: previa ligera del dia.
Register-FutbolTask "futbol_release_sat" "scripts\windows\editorial_release.ps1" "11:00" @("Saturday") "-PublishLimit 2" 2
# Domingo: cierre ligero, sin invadir el digest de las 22:00.
Register-FutbolTask "futbol_release_sun" "scripts\windows\editorial_release.ps1" "21:15" @("Sunday") "-PublishLimit 2" 2

# --- Catch-up de publicacion (T+30min tras cada release) ---
# Si el release dispatchea una pieza pero el browser publish falla a mitad de batch,
# la pieza queda con status=published y external_publication_ref=None. Estas tareas
# rescatan esos casos llamando auto_publish_browser.ps1 dentro de la misma ventana
# del slot, sin esperar al siguiente dia.
Register-FutbolTask "futbol_publish_catchup_weekday_morning" "scripts\windows\auto_publish_browser.ps1" "10:00" @("Monday","Tuesday","Wednesday","Thursday","Friday") "-Limit 2" 2
Register-FutbolTask "futbol_publish_catchup_weekday_evening" "scripts\windows\auto_publish_browser.ps1" "20:00" @("Monday","Tuesday","Wednesday","Thursday","Friday") "-Limit 2" 2
Register-FutbolTask "futbol_publish_catchup_sat" "scripts\windows\auto_publish_browser.ps1" "11:30" @("Saturday") "-Limit 2" 2
Register-FutbolTask "futbol_publish_catchup_sun" "scripts\windows\auto_publish_browser.ps1" "21:45" @("Sunday") "-Limit 2" 2

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
