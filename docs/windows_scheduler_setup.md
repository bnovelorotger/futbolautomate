# Automatizacion Windows con PowerShell y Task Scheduler

Windows es el entorno principal actual de operacion de uFutbolBalear. La automatizacion se hace con PowerShell y el Programador de tareas de Windows, sin WSL y sin mover logica al backend.

## Principios

- PowerShell es la capa externa de orquestacion
- toda la logica sigue en `app.pipelines.*`
- no hay scheduler interno
- no hay autopublicacion en X
- Typefully es el panel operativo final
- la produccion v1 congela el scope automatico y no anade nuevas familias de contenido

## Scripts activos

Ruta: `scripts/windows/`

- `common.ps1`
  - carga `.env` y `.env.windows`
  - resuelve el root del proyecto
  - usa `.venv\Scripts\python.exe` si existe
  - crea `logs\` y `.locks\`
  - escribe logs con timestamp
  - evita solapes con lock file exclusivo
- `refresh_data.ps1`
  - siembra competiciones integradas si faltan
  - refresca explicitamente `matches` y `standings` de:
    - `tercera_rfef_g11`
    - `segunda_rfef_g3_baleares`
    - `division_honor_mallorca`
- `readiness_check.ps1`
  - ejecuta `competition_catalog status --integrated-only`
  - ejecuta `system_check editorial-readiness`
- `run_editorial_day.ps1`
  - ejecuta `preview-day`
  - aborta si `preview-day` falla
  - si `PREVIEW_ONLY=true` o `-PreviewOnly`, termina sin `run-daily`
  - si no, ejecuta `run-daily`
- `editorial_release.ps1`
  - ejecuta `editorial_release dry-run` o `run`
  - el pipeline interno hace `quality_checks -> autoapprove -> dispatch -> autoexport`
  - en produccion v1 solo empuja a Typefully:
    - `results_roundup`
    - `standings_roundup`
    - `preview`
    - `ranking`
- `typefully_autoexport.ps1`
  - ejecuta `typefully_autoexport dry-run` o `run`
  - queda como utilidad diagnostica o manual
  - el carril v1 recomendado pasa por `editorial_release`
- `run_slot.ps1`
  - wrapper opcional para `refresh`, `readiness`, `editorial-day`, `editorial-release` y `autoexport`

## Variables y entorno

Orden de carga:

1. `.env`
2. `.env.windows`

Variables utiles:

```powershell
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/futbol_balear
TYPEFULLY_API_KEY=tu_api_key
TYPEFULLY_API_URL=https://api.typefully.com
PYTHON_BIN=C:\Users\bnove\Documents\futbolbalear\.venv\Scripts\python.exe
APP_TIMEZONE=Europe/Madrid
```

Si `PYTHON_BIN` no esta definido, el script intenta usar:

1. `.venv\Scripts\python.exe`
2. `python.exe` del sistema

## Logs

Logs operativos:

- `logs\cron_refresh.log`
- `logs\cron_readiness.log`
- `logs\cron_editorial.log`
- `logs\cron_release.log`
- `logs\cron_autoexport.log`

Cada linea incluye:

- timestamp local
- nivel (`INFO`, `WARN`, `ERROR`)
- paso ejecutado

## Produccion v1

Frontera automatica cerrada:

- `results_roundup`
- `standings_roundup`
- `preview`
- `ranking`

Todo lo demas queda manual en esta fase:

- `match_result`
- `standings`
- `featured_match_preview`
- `featured_match_event`
- `standings_event`
- `form_event`
- `form_ranking`
- `stat_narrative`
- `metric_narrative`
- `viral_story`

La politica activa de autoexport vive en `app/config/typefully_autoexport.json`:

- `enabled=true`
- `phase=1`
- `allowed_content_types=results_roundup, standings_roundup, preview, ranking`
- `max_exports_per_run=5`

`phase=2` y `phase=3` quedan congeladas con la misma frontera v1 durante esta iteracion.

## Ejecucion manual exacta

Desde PowerShell en la raiz del proyecto:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\refresh_data.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\readiness_check.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\run_editorial_day.ps1" -TargetDate 2026-03-17
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\editorial_release.ps1" -TargetDate 2026-03-17 -DryRun
python -m app.pipelines.editorial_approval dry-run --date 2026-03-17
python -m app.pipelines.editorial_release dry-run --date 2026-03-17
python -m app.pipelines.typefully_autoexport status
python -m app.pipelines.typefully_autoexport pending-capacity
```

Modo seguro de primer despliegue:

```powershell
$env:PREVIEW_ONLY = "true"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\run_editorial_day.ps1" -TargetDate 2026-03-17
Remove-Item Env:PREVIEW_ONLY
```

O equivalente por parametro:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\run_editorial_day.ps1" -TargetDate 2026-03-17 -PreviewOnly
```

## Task Scheduler

Configuracion recomendada:

- `uFutbolBalear Refresh`
- `uFutbolBalear Readiness`
- `uFutbolBalear Editorial Day`
- `uFutbolBalear Editorial Release`

Accion base:

```text
Program/script: powershell.exe
Start in: C:\Users\bnove\Documents\futbolbalear
```

En `Settings`:

- activar `Run task as soon as possible after a scheduled start is missed`
- marcar `If the task is already running, then the following rule applies: Do not start a new instance`

### Triggers recomendados

- Lunes
  - Refresh: `08:35`
  - Readiness: `08:45`
  - Editorial Day: `09:00`
  - Editorial Release: `09:20`
- Miercoles
  - Refresh: `10:30`
  - Readiness: `10:45`
  - Editorial Day: `11:00`
  - Editorial Release: `11:20`
- Viernes
  - Refresh: `09:30`
  - Readiness: `09:45`
  - Editorial Day: `10:00`
  - Editorial Release: `10:20`
- Domingo
  - Refresh: `20:00`
  - Readiness: `20:15`
  - Editorial Day: `20:30`
  - Editorial Release: `20:50`

### Acciones exactas

Refresh:

```text
Program/script: powershell.exe
Add arguments: -NoProfile -ExecutionPolicy Bypass -File "C:\Users\bnove\Documents\futbolbalear\scripts\windows\refresh_data.ps1"
Start in: C:\Users\bnove\Documents\futbolbalear
```

Readiness:

```text
Program/script: powershell.exe
Add arguments: -NoProfile -ExecutionPolicy Bypass -File "C:\Users\bnove\Documents\futbolbalear\scripts\windows\readiness_check.ps1"
Start in: C:\Users\bnove\Documents\futbolbalear
```

Editorial Day:

```text
Program/script: powershell.exe
Add arguments: -NoProfile -ExecutionPolicy Bypass -File "C:\Users\bnove\Documents\futbolbalear\scripts\windows\run_editorial_day.ps1"
Start in: C:\Users\bnove\Documents\futbolbalear
```

Editorial Release en modo seguro:

```text
Program/script: powershell.exe
Add arguments: -NoProfile -ExecutionPolicy Bypass -File "C:\Users\bnove\Documents\futbolbalear\scripts\windows\editorial_release.ps1" -DryRun
Start in: C:\Users\bnove\Documents\futbolbalear
```

Editorial Release en modo real:

```text
Program/script: powershell.exe
Add arguments: -NoProfile -ExecutionPolicy Bypass -File "C:\Users\bnove\Documents\futbolbalear\scripts\windows\editorial_release.ps1"
Start in: C:\Users\bnove\Documents\futbolbalear
```

## Flujo recomendado de activacion

1. ejecutar manualmente `refresh_data.ps1`
2. ejecutar manualmente `readiness_check.ps1`
3. ejecutar manualmente `run_editorial_day.ps1 -PreviewOnly`
4. ejecutar manualmente `editorial_release.ps1 -DryRun`
5. revisar:
   - `logs\cron_refresh.log`
   - `logs\cron_readiness.log`
   - `logs\cron_editorial.log`
   - `logs\cron_release.log`
6. revisar `python -m app.pipelines.typefully_autoexport status`
7. si todo es correcto, crear las tareas en Task Scheduler
8. quitar `-PreviewOnly` y `-DryRun` cuando el comportamiento ya sea estable

## Editorial Release como panel operativo v1

El flujo recomendado es:

1. `Refresh`
2. `Readiness`
3. `Editorial Day`
4. `Editorial Release`

`Editorial Release` hace internamente:

- `editorial_approval_policy`
- `editorial_quality_checks`
- `publication_dispatch`
- `typefully_autoexport`

Con eso, Typefully pasa a ser el panel real para las piezas seguras de produccion v1.

## Capacidad de Typefully

Si el plan de Typefully devuelve `MONETIZATION_ERROR`, el sistema lo trata como limite de capacidad del canal:

- las piezas pasan a `pending-capacity`
- siguen siendo reintentables
- no se cuentan como fallo tecnico real
- el resumen separa `capacity_deferred_count` de `failed_count`

Estrategia recomendada:

1. mantener `max_exports_per_run=5`
2. revisar `pending-capacity`
3. reintentar con `python -m app.pipelines.typefully_autoexport run --date <fecha>` cuando liberes drafts o amplíes plan

## Tareas que siguen siendo manuales

- revisar drafts en `editorial_queue`
- `approve/reject` de piezas fuera de la frontera v1
- `publication_dispatch` de piezas sensibles
- `typefully_export` manual de cualquier pieza que falle `editorial_quality_checks`
- edicion final y programacion dentro de Typefully

## Limitaciones abiertas

- no hay rotacion automatica de logs en Windows; la limpieza es manual por ahora
- el lock evita duplicados del mismo slot, pero no sustituye la opcion `Do not start a new instance` de Task Scheduler
- el scheduler no resuelve logica editorial por hora; solo dispara scripts
