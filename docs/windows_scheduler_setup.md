# Automatizacion Windows con PowerShell y Task Scheduler

Windows es el entorno principal de operacion de futbolbalear. La automatizacion se hace con PowerShell y el Programador de tareas de Windows.

## Principios

- PowerShell es la capa externa de orquestacion; toda la logica vive en `app.pipelines.*`
- No hay scheduler interno: el Programador de tareas de Windows es la unica fuente de verdad de horarios
- `editorial_release` activa por defecto la publicacion en X via navegador (`--publish-browser`)
- X API directa desactivada por defecto (sin acceso de escritura a la API v2 de X)
- El handoff final es `exports/export_base.json`

---

## Scripts activos

Ruta: `scripts/windows/`

| Script | Descripcion |
|--------|-------------|
| `common.ps1` | Carga `.env`, resuelve Python, crea `logs/` y `.locks/`, escribe logs con timestamp, evita solapamientos con lock file |
| `refresh_data.ps1` | Scraping de matches y standings para las 7 competiciones integradas |
| `readiness_check.ps1` | `competition_catalog status` + `system_check editorial-readiness` |
| `run_editorial_day.ps1` | `preview-day` + `run-daily` (generacion de contenido editorial) |
| `editorial_release.ps1` | Quality checks + aprobacion + dispatch + export + publicacion en X via navegador |
| `editorial_day_plan.ps1` | Agenda editorial diaria para Telegram a las 09:00 con lo previsto del dia |
| `editorial_daily_digest.ps1` | Resumen editorial diario para Telegram a las 22:00 con lo publicado y ratios |
| `daily_engagement.ps1` | Likes diarios en el timeline de X para humanizar la cuenta (3 likes/dia por defecto) |
| `backup_db.ps1` | Backup diario de PostgreSQL en `backups/` |
| `auto_publish_browser.ps1` | Reintento batch canonico de publicacion via navegador, desacoplado del release |
| `check_browser_session.ps1` | Comprueba que `.x_browser_state.json` existe y que la sesion de X esta activa; alerta si ha caducado |
| `cleanup_logs.ps1` | Elimina archivos `.bak` de logs con mas de 30 dias de antiguedad |
| `setup_scheduler.ps1` | Crea o recrea todas las tareas en el Programador de tareas (ejecutar como Admin) |

---

## Horario de tareas por dia

Todas las tareas usan `-LogonType Interactive`: requieren sesion de Windows abierta (la pantalla puede estar bloqueada).

| Tarea | Lun | Mar | Mie | Jue | Vie | Sab | Dom |
|-------|-----|-----|-----|-----|-----|-----|-----|
| `futbol_session_check` | 06:00 | — | — | — | — | — | — |
| `futbol_refresh_morning` | 06:30 | — | — | — | — | — | 06:30 |
| `futbol_refresh_midweek` | — | — | 07:00 | — | 07:00 | — | — |
| `futbol_refresh_other` | — | 07:00 | — | 07:00 | — | 07:00 | — |
| `futbol_refresh_afternoon` | 14:00 | 14:00 | 14:00 | 14:00 | 14:00 | 14:00 | 14:00 |
| `futbol_editorial_day_mon_sun` | 07:30 | — | — | — | — | — | 07:30 |
| `futbol_editorial_day_wed` | — | — | 18:30 | — | — | — | — |
| `futbol_editorial_day_fri` | — | — | — | — | 08:00 | — | — |
| `futbol_editorial_day_other` | — | 09:00 | — | 09:00 | — | 09:00 | — |
| `futbol_release_mon_sun` | 08:30 | — | — | — | — | — | 08:30 |
| `futbol_release_wed` | — | — | 19:30 | — | — | — | — |
| `futbol_release_fri` | — | — | — | — | 09:00 | — | — |
| `futbol_release_other` | — | 10:30 | — | 10:30 | — | 10:30 | — |
| `futbol_editorial_day_plan` | 09:00 | 09:00 | 09:00 | 09:00 | 09:00 | 09:00 | 09:00 |
| `futbol_editorial_digest` | 22:00 | 22:00 | 22:00 | 22:00 | 22:00 | 22:00 | 22:00 |
| `futbol_engagement` | 12:30 | 12:30 | 12:30 | 12:30 | 12:30 | — | — |
| `futbol_backup` | 03:00 | 03:00 | 03:00 | 03:00 | 03:00 | 03:00 | 03:00 |
| `futbol_log_cleanup` | — | — | — | — | — | — | 04:00 |

**Logica de secuencia por dia activo:**
- Lunes: session check a las 06:00 → refresh a las 06:30 → editorial a las 07:30 → release (+ publicacion en X) a las 08:30
- Domingo: refresh a las 06:30 → editorial a las 07:30 → release (+ publicacion en X) a las 08:30
- Miercoles: refresh a las 07:00 → editorial a las 18:30 → release (+ publicacion en X) a las 19:30
- Viernes: refresh a las 07:00 → editorial a las 08:00 → release (+ publicacion en X) a las 09:00
- Martes/jueves/sabado: solo refresh matutino + release estandar a las 10:30
- todos los dias: agenda Telegram a las 09:00 y digest Telegram a las 22:00

---

## Publicacion automatica en X via navegador

El pipeline publica en X usando Playwright con Chromium en modo visible (`headless=False`). No requiere API key de X.

### Como funciona

1. `editorial_release.ps1` llama a `editorial_release run --publish-browser`
2. `XBrowserPublicationService` busca candidatos `published` sin `external_publication_ref` de las ultimas 48h
3. Para cada candidato: abre Chromium, navega a `x.com/compose/post`, escribe el texto, espera que el boton Post este activo y envia con `Ctrl+Enter`
4. Verifica que X navega fuera de `/compose/post` (confirmacion de exito)
5. Guarda `external_publication_ref=x-browser:<timestamp>` y `external_channel=x` en BD

### Requisitos para que funcione

- El archivo `.x_browser_state.json` debe existir en la raiz del proyecto (sesion de X guardada)
- La sesion de Windows debe estar abierta (Interactive logon) — la pantalla puede estar bloqueada
- Chromium instalado: `playwright install chromium`

### Intervalo entre tweets

15 minutos entre tweets (`X_BROWSER_STAGGER_SECONDS=900`). Con varios candidatos pendientes la tarea puede durar `n * 15 minutos`.

### Si la sesion de X expira

```powershell
python -m app.pipelines.x_publish browser-auth-capture
```

Abre un navegador interactivo para hacer login. Guarda la sesion en `.x_browser_state.json`. El archivo esta en `.gitignore` y nunca se sube al repositorio.

### Reintento manual de publicacion

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\auto_publish_browser.ps1"
```

### Script de diagnostico

```bash
python scripts/debug_browser_publish.py
```

Abre Chromium visible con `slow_mo=300` y publica un tweet de prueba. Util para verificar que la sesion esta activa y que el flujo funciona antes de dejarlo en automatico.

---

## Engagement automatico

`futbol_engagement` se ejecuta de lunes a viernes a las 12:30. Da like a tweets del timeline de X para mantener la cuenta activa.

Configuracion en `.env`:
```
X_ENGAGEMENT_DAILY_LIKES=3
```

---

## Variables de entorno clave

Orden de carga: `.env` → `.env.windows`

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/futbol_balear
PYTHON_BIN=C:\Users\bnove\Documents\futbolbalear\.venv\Scripts\python.exe

# Browser publisher
X_BROWSER_STATE_FILE=.x_browser_state.json
X_BROWSER_HEADLESS=false
X_BROWSER_TYPING_DELAY_MS=30
X_BROWSER_STAGGER_SECONDS=900

# Engagement
X_ENGAGEMENT_DAILY_LIKES=3
```

---

## Logs

| Archivo | Tarea |
|---------|-------|
| `logs\cron_refresh.log` | refresh_data |
| `logs\cron_readiness.log` | readiness_check |
| `logs\cron_editorial.log` | run_editorial_day |
| `logs\cron_release.log` | editorial_release |
| `logs\editorial_day_plan.log` | editorial_day_plan |
| `logs\editorial_daily_digest.log` | editorial_daily_digest |
| `logs\cron_engagement.log` | daily_engagement |
| `logs\cron_backup.log` | backup_db |
| `logs\cron_session_check.log` | check_browser_session |
| `logs\cron_cleanup.log` | cleanup_logs |

---

## Verificacion de sesion de X browser

`futbol_session_check` se ejecuta los lunes a las 06:00, antes del scraping matutino (06:30) y la ventana de publicacion (08:30).

### Que hace

1. Comprueba que `.x_browser_state.json` existe en la raiz del proyecto
2. Llama a `python -m app.pipelines.x_publish browser-auth-verify`, que valida la sesion guardada en `.x_browser_state.json`
3. Registra el resultado en `logs\cron_session_check.log`

### Que hacer si se dispara la alerta ERROR

Si el log contiene `ALERTA: Sesion de X browser caducada`, renovar la sesion antes de que llegue la ventana de publicacion:

```powershell
python -m app.pipelines.x_publish browser-auth-capture
```

Abre un navegador interactivo para hacer login. Guarda la sesion en `.x_browser_state.json`. El archivo esta en `.gitignore` y nunca se sube al repositorio.

### Por que solo los lunes

El lunes es el dia de mayor carga de publicacion (resultados del fin de semana). Un aviso a las 06:00 da tiempo de actuar antes de las 08:30 cuando arranca `editorial_release`. Si la sesion caduca otro dia, el diagnostico manual con `python scripts/debug_browser_publish.py` o el log de `editorial_release` lo detectara igualmente.

---

## Recrear las tareas desde cero

Ejecutar como Administrador:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\scripts\windows\setup_scheduler.ps1"
```

Verificar que se crearon:

```powershell
Get-ScheduledTask | Where-Object { $_.TaskName -like "futbol_*" } | Select-Object TaskName, State | Format-Table
```

---

## Parametros de editorial_release.ps1

```powershell
.\scripts\windows\editorial_release.ps1 [-TargetDate YYYY-MM-DD] [-DryRun] [-PublishBrowser] [-SkipPublishBrowser] [-PublishX] [-SkipPublishX] [-PublishTypefully]
```

- Por defecto: `run` + `--publish-browser` (sin fecha = hoy)
- `-DryRun`: simula sin escribir nada en BD ni publicar
- `-SkipPublishBrowser`: omite la publicacion via navegador
- `-PublishX`: alias legacy que delega en `--publish-browser`
- `-SkipPublishX`: alias legacy que delega en `-SkipPublishBrowser`
- `-PublishTypefully`: compatibilidad/manual; no forma parte del carril programado por defecto

---

## Flujo completo de editorial_release

`editorial_release run --publish-browser` ejecuta internamente:

1. `editorial_quality_checks` — valida calidad de los borradores
2. `editorial_approval_policy` — autoaprueba segun reglas del dia
3. `publication_dispatcher` — mueve candidatos aprobados a `published`
4. `export_base_service` → `exports/export_base.json`
5. `XBrowserPublicationService.publish_pending()` — marca como omitidos los candidatos publicados hace mas de 48h y publica los candidatos recientes pendientes con el mismo backend del retry batch

---

## Frontera de autoaprobacion v1

**Siempre autoaprobados:**
- `results_roundup`, `standings_roundup`, `preview`, `ranking`

**Lunes:**
- `top_scorer_update`

**Martes/miercoles (si pasan quality checks):**
- `stat_narrative`, `metric_narrative`, `viral_story`

**Viernes:**
- `featured_match_preview`, `match_impact_scenario`

**Siempre manuales:**
- `match_result`, `standings`, `featured_match_event`, `race_narrative`, `milestone_story`, `standings_event`, `form_event`, `form_ranking`

---

## Ejecucion manual

```powershell
# Scraping
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\refresh_data.ps1"

# Verificacion de salud
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\readiness_check.ps1"

# Generacion de contenido
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\run_editorial_day.ps1" -TargetDate 2026-05-16

# Release en modo simulacion
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\editorial_release.ps1" -DryRun

# Release real con publicacion en X
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\editorial_release.ps1"

# Solo publicacion via navegador (reintento)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\auto_publish_browser.ps1"

# Diagnostico de sesion del navegador
python scripts/debug_browser_publish.py
```

---

## Telegram, agenda y digest diario

La operativa de Telegram tiene tres piezas distintas:

- notificaciones de evento (`inicio`, `fin`, `error`) emitidas por las tareas ya existentes
- una agenda editorial a las `09:00`
- un digest diario a las `22:00`

Reglas operativas:

- no crear una tarea separada solo para `inicio`/`fin`/`error`; esas notificaciones deben salir desde el wrapper de cada tarea critica
- la agenda editorial debe programarse a las `09:00` y enviarse por Telegram con `scripts/windows/editorial_day_plan.ps1 -SendTelegram`
- el digest diario debe programarse a las `22:00` y enviarse por Telegram con `scripts/windows/editorial_daily_digest.ps1 -SendTelegram`
- usar el mismo patron operativo de `common.ps1`: `.env`, logs y lock file

Referencia de mensajes, ratios y prueba manual:

- ver [telegram_notifications_runbook.md](C:/Users/bnove/Documents/futbolbalear/docs/telegram_notifications_runbook.md)

---

## Limitaciones conocidas

- Los logs rotan automaticamente al superar 5 MB (hasta 3 archivos `.bak` por log); `futbol_log_cleanup` elimina los `.bak` con mas de 30 dias cada domingo a las 04:00
- El lock previene solapamientos del mismo slot, pero Task Scheduler debe tener `Do not start a new instance` activado como segunda linea de defensa
- `headless=False` requiere sesion de Windows interactiva; no funciona en sesiones de servicio (SYSTEM)
- Si el ordenador entra en suspension durante una publicacion en curso, Playwright puede quedar colgado; el lock file evita reinicio automatico hasta que se libere manualmente
