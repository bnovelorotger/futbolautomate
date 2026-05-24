# Automatizacion Windows con PowerShell y Task Scheduler

Windows es el entorno principal de operacion de futbolbalear. La automatizacion se hace con PowerShell y el Programador de tareas de Windows.

## Principios

- PowerShell es la capa externa de orquestacion; la logica vive en `app.pipelines.*`.
- No hay scheduler interno: Task Scheduler es la fuente de verdad de horarios.
- `editorial_release.ps1` publica en X via navegador por defecto (`--publish-browser`).
- El plan de Telegram sale a las 08:00 y el digest diario a las 22:00.
- La parrilla editorial vigente esta documentada en [x_publication_weekly_grid.md](C:/Users/bnove/Documents/futbolbalear/docs/x_publication_weekly_grid.md).

## Scripts activos

| Script | Descripcion |
| --- | --- |
| `common.ps1` | Carga `.env`, resuelve Python, crea logs y locks, evita solapes por lock file |
| `refresh_data.ps1` | Scraping de partidos, clasificaciones y datos base |
| `run_editorial_day.ps1` | `preview-day` + `run-daily`, genera contenido editorial |
| `editorial_release.ps1` | Quality checks, autoapproval, dispatch, export y publicacion en X via navegador |
| `editorial_day_plan.ps1` | Agenda editorial diaria para Telegram |
| `editorial_daily_digest.ps1` | Digest editorial diario para Telegram |
| `daily_engagement.ps1` | Likes diarios controlados en X |
| `check_browser_session.ps1` | Verifica que la sesion browser de X sigue activa |
| `backup_db.ps1` | Backup diario de BD |
| `cleanup_logs.ps1` | Limpieza semanal de logs antiguos |
| `setup_scheduler.ps1` | Crea o recrea todas las tareas programadas |

## Horario de tareas

Todas las tareas usan `-LogonType Interactive`, por lo que requieren una sesion de Windows abierta. La pantalla puede estar bloqueada.

| Tarea | Lun | Mar | Mie | Jue | Vie | Sab | Dom |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `futbol_session_check` | 06:00 | - | - | - | - | - | - |
| `futbol_refresh_morning` | 06:30 | - | - | - | - | - | 06:30 |
| `futbol_refresh_midweek` | - | - | 07:00 | - | 07:00 | - | - |
| `futbol_refresh_other` | - | 07:00 | - | 07:00 | - | 07:00 | - |
| `futbol_refresh_afternoon` | 14:00 | 14:00 | 14:00 | 14:00 | 14:00 | 14:00 | 14:00 |
| `futbol_refresh_sunday_evening` | - | - | - | - | - | - | 20:00 |
| `futbol_editorial_day_mon` | 07:30 | - | - | - | - | - | - |
| `futbol_editorial_day_other` | - | 08:30 | - | 08:30 | - | - | - |
| `futbol_editorial_day_wed` | - | - | 08:30 | - | - | - | - |
| `futbol_editorial_day_fri` | - | - | - | - | 08:00 | - | - |
| `futbol_editorial_day_sat` | - | - | - | - | - | 09:30 | - |
| `futbol_editorial_day_sun` | - | - | - | - | - | - | 20:45 |
| `futbol_release_weekday_morning` | 09:30 | 09:30 | 09:30 | 09:30 | 09:30 | - | - |
| `futbol_release_weekday_evening` | 19:30 | 19:30 | 19:30 | 19:30 | 19:30 | - | - |
| `futbol_release_sat` | - | - | - | - | - | 11:00 | - |
| `futbol_release_sun` | - | - | - | - | - | - | 21:15 |
| `futbol_publish_catchup_weekday_morning` | 10:00 | 10:00 | 10:00 | 10:00 | 10:00 | - | - |
| `futbol_publish_catchup_weekday_evening` | 20:00 | 20:00 | 20:00 | 20:00 | 20:00 | - | - |
| `futbol_publish_catchup_sat` | - | - | - | - | - | 11:30 | - |
| `futbol_publish_catchup_sun` | - | - | - | - | - | - | 21:45 |
| `futbol_editorial_day_plan` | 08:00 | 08:00 | 08:00 | 08:00 | 08:00 | 08:00 | 08:00 |
| `futbol_summary` | 21:00 | 21:00 | 21:00 | 21:00 | 21:00 | 21:00 | 21:00 |
| `futbol_editorial_digest` | 22:00 | 22:00 | 22:00 | 22:00 | 22:00 | 22:00 | 22:00 |
| `futbol_engagement` | 12:30 | 12:30 | 12:30 | 12:30 | 12:30 | - | - |
| `futbol_backup` | 03:00 | 03:00 | 03:00 | 03:00 | 03:00 | 03:00 | 03:00 |
| `futbol_log_cleanup` | - | - | - | - | - | - | 04:00 |
| `futbol_stats_backfill_weekly` | - | 05:00 | - | - | - | - | - |

## Secuencia por dia activo

- Lunes: session check 06:00, refresh 06:30, editorial 07:30, plan Telegram 08:00, releases 09:30 y 19:30 con `-PublishLimit 2`.
- Martes: refresh 07:00, editorial 08:30, releases 09:30 y 19:30 con `-PublishLimit 2`.
- Miercoles: refresh 07:00, editorial 08:30, releases 09:30 y 19:30 con `-PublishLimit 2`.
- Jueves: refresh 07:00, editorial 08:30, releases 09:30 y 19:30 con `-PublishLimit 2`.
- Viernes: refresh 07:00, editorial 08:00, releases 09:30 y 19:30 con `-PublishLimit 2`.
- Sabado: refresh 07:00, editorial 09:30, release 11:00 con `-PublishLimit 2`.
- Domingo: refresh 06:30, refresh 14:00, refresh extra 20:00, editorial 20:45, release 21:15 con `-PublishLimit 2`.

### Backfill semanal de estadisticas

`futbol_stats_backfill_weekly` (martes 05:00) corre
`scripts/windows/backfill_stats.ps1` con
`-Season 2025-26 -DataTypes results,standings,scorers,halftime -LimitPerCompetition 250 -IncludeErrors`.
Reporta cobertura de resultados/clasificacion (`stat_coverage report`) y
reintenta goleadores pendientes/parciales (`match_events enrich-pending`) en
todas las competiciones integradas. Detalle en `docs/data_coverage.md`.

## Publicacion automatica en X via navegador

El pipeline publica en X usando Playwright con Chromium visible (`headless=False`). No requiere API de X.

Requisitos:

- `.x_browser_state.json` en la raiz del proyecto.
- Sesion de Windows abierta.
- Chromium instalado con `playwright install chromium`.

Configuracion relevante:

```env
X_BROWSER_STATE_FILE=.x_browser_state.json
X_BROWSER_HEADLESS=false
X_BROWSER_TYPING_DELAY_MS=30
X_BROWSER_STAGGER_SECONDS=1800
X_BROWSER_RELEASE_ACTION_LIMIT=4
```

`X_BROWSER_RELEASE_ACTION_LIMIT=4` es el techo global. Cada tarea puede bajar ese techo con `-PublishLimit`; los slots L-V y fin de semana usan `-PublishLimit 2`.

## Ventanas de publicacion

`app/config/publication_schedule.json` controla que tipos son publicables por dia y el cupo por slot:

- lunes desde `09:30` y `19:30`: `results_roundup`, `standings_roundup`, `top_scorer_update`, `race_narrative`, `milestone_story`
- martes desde `09:30` y `19:30`: `ranking`, `standings_roundup`
- miercoles desde `09:30` y `19:30`: `viral_story`, `metric_narrative`, `stat_narrative`
- jueves desde `09:30` y `19:30`: `top_scorer_update`, `ranking`
- viernes desde `09:30` y `19:30`: `featured_match_preview`, `match_impact_scenario`
- sabado desde `11:00`: `preview`
- domingo desde `21:15`: `results_roundup`, `standings_roundup`

El release tambien filtra por frescura editorial real con `EditorialCandidateWindowService`, para evitar rescatar piezas caducadas.

## Recrear tareas

Ejecutar como Administrador desde la raiz del proyecto:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\scripts\windows\setup_scheduler.ps1"
```

Verificar:

```powershell
Get-ScheduledTask | Where-Object { $_.TaskName -like "futbol_*" } | Select-Object TaskName, State | Format-Table
```

El script elimina tareas legacy ya sustituidas:

- `futbol_editorial_day_mon_sun`
- `futbol_editorial_day_other`
- `futbol_release_mon`
- `futbol_release_mon_sun`
- `futbol_release_other`
- `futbol_release_wed`
- `futbol_release_fri`
- `futbol_publish_catchup_mon`
- `futbol_publish_catchup_tue`
- `futbol_publish_catchup_wed`
- `futbol_publish_catchup_thu`
- `futbol_publish_catchup_fri`

## Parametros de `editorial_release.ps1`

```powershell
.\scripts\windows\editorial_release.ps1 [-TargetDate YYYY-MM-DD] [-DryRun] [-Limit N] [-PublishLimit N] [-PublishBrowser] [-SkipPublishBrowser] [-PublishX] [-SkipPublishX] [-PublishTypefully]
```

- Por defecto: `run` + `--publish-browser`.
- `-PublishLimit N`: baja el maximo de publicacion de este run sin superar `X_BROWSER_RELEASE_ACTION_LIMIT`.
- `-Limit N`: alias legacy que se reinterpreta como `-PublishLimit N` cuando no se pasa `-PublishLimit`.
- `-DryRun`: simula sin persistir ni publicar.
- `-SkipPublishBrowser`: omite publicacion via navegador.
- `-PublishX` y `-SkipPublishX`: aliases legacy.

## Telegram

La operativa normal envia:

- agenda editorial diaria a las 08:00
- aviso por cada post publicado
- digest diario a las 22:00
- alertas de error de tareas criticas

No se envian mensajes de inicio/fin de tarea salvo que se active explicitamente `TELEGRAM_TASK_START_FINISH_ENABLED=true`.

## Sesion de X

Si la sesion caduca:

```powershell
python -m app.pipelines.x_publish browser-auth-capture
```

Verificacion manual:

```powershell
python -m app.pipelines.x_publish browser-auth-verify
```

## Limitaciones

- `headless=False` requiere sesion interactiva de Windows.
- Si el equipo duerme durante una publicacion, Playwright puede quedarse colgado hasta que se libere el lock.
- Los slots de release tienen margen de 2-3 horas para respetar el stagger sin que Task Scheduler corte el proceso.
- Las publicaciones fuera de parrilla deben hacerse manualmente o con `auto_publish_browser.ps1` bajo supervision.
