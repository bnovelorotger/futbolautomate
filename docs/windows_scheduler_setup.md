# Automatizacion Windows con PowerShell y Task Scheduler

Windows es el entorno principal actual de operacion de uFutbolBalear. La automatizacion se hace con PowerShell y el Programador de tareas de Windows, sin WSL y sin mover logica al backend.

## Principios

- PowerShell es la capa externa de orquestacion
- toda la logica sigue en `app.pipelines.*`
- no hay scheduler interno
- no hay autopublicacion
- `editorial_queue`, `approve/reject` y la edicion final en Typefully siguen siendo manuales
- Linux cron queda como opcion futura de despliegue

## Scripts creados

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
  - refresca explicitamente:
    - `tercera_rfef_g11` -> `matches`, `standings`
    - `segunda_rfef_g3_baleares` -> `matches`, `standings`
    - `division_honor_mallorca` -> `matches`, `standings`
- `readiness_check.ps1`
  - ejecuta `competition_catalog status --integrated-only`
  - ejecuta `system_check editorial-readiness`
- `run_editorial_day.ps1`
  - ejecuta `preview-day`
  - aborta si `preview-day` falla
  - si `PREVIEW_ONLY=true` o `-PreviewOnly`, termina sin `run-daily`
  - si no, ejecuta `run-daily`
- `run_slot.ps1`
  - wrapper opcional para `refresh`, `readiness`, `editorial-day`, `editorial-release` y `autoexport`
- `typefully_autoexport.ps1`
  - ejecuta `typefully_autoexport dry-run` o `run`
  - el pipeline interno hace `quality_checks -> autoexport`
  - soporta `-TargetDate`, `-DryRun`, `-UseDraft` y `-UseRewrite`
  - usa un slot separado para que la autoexportacion nunca quede acoplada a `run-daily`
  - la politica activa se controla por `enabled=true` y `phase=<1|2|3>` en `app/config/typefully_autoexport.json`
  - aplica politica de capacidad: `max_exports_per_run`, `max_exports_per_day` y `capacity_error_codes`
- `editorial_release.ps1`
  - ejecuta `editorial_release dry-run` o `run`
  - el pipeline interno hace `quality_checks -> autoapprove -> dispatch -> autoexport`
  - solo empuja a Typefully `match_result`, `standings`, `preview` y `ranking` si pasan quality checks
  - mantiene `stat_narrative`, `metric_narrative` y `viral_story` en revision manual

## Variables y entorno

Orden de carga:

1. `.env`
2. `.env.windows`

Esto permite que `.env.windows` sobrescriba ajustes locales especificos de Windows.

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

Se reutiliza una estrategia sencilla y estable:

- `logs\cron_refresh.log`
- `logs\cron_readiness.log`
- `logs\cron_editorial.log`
- `logs\cron_release.log`
- `logs\cron_autoexport.log`

Cada linea incluye:

- timestamp local
- nivel (`INFO`, `WARN`, `ERROR`)
- paso ejecutado

## Ejecucion manual exacta

Desde PowerShell en la raiz del proyecto:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\refresh_data.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\readiness_check.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\run_editorial_day.ps1" -TargetDate 2026-03-16
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\editorial_release.ps1" -TargetDate 2026-03-16 -DryRun
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\typefully_autoexport.ps1" -TargetDate 2026-03-16 -DryRun
python -m app.pipelines.typefully_autoexport status
python -m app.pipelines.typefully_autoexport pending-capacity
python -m app.pipelines.editorial_approval status
python -m app.pipelines.editorial_quality_checks check-pending
```

Modo seguro de primer despliegue:

```powershell
$env:PREVIEW_ONLY = "true"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\run_editorial_day.ps1" -TargetDate 2026-03-16
Remove-Item Env:PREVIEW_ONLY
```

O equivalente por parametro:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\run_editorial_day.ps1" -TargetDate 2026-03-16 -PreviewOnly
```

## Task Scheduler

Configuracion recomendada:

- crea tres tareas:
- crea tres tareas base:
  - `uFutbolBalear Refresh`
  - `uFutbolBalear Readiness`
  - `uFutbolBalear Editorial Day`
- y una cuarta tarea recomendada:
  - `uFutbolBalear Editorial Release`
- usa `powershell.exe`
- argumento base:
  - `-NoProfile -ExecutionPolicy Bypass -File "C:\Users\bnove\Documents\futbolbalear\scripts\windows\refresh_data.ps1"`
- `Start in`:
  - `C:\Users\bnove\Documents\futbolbalear`
- en `Settings`:
  - activar `Run task as soon as possible after a scheduled start is missed`
  - marcar `If the task is already running, then the following rule applies: Do not start a new instance`

### Triggers recomendados

La equivalencia con el cron simplificado actual es:

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

Primer despliegue seguro de `Editorial Day`:

```text
Program/script: powershell.exe
Add arguments: -NoProfile -ExecutionPolicy Bypass -File "C:\Users\bnove\Documents\futbolbalear\scripts\windows\run_editorial_day.ps1" -PreviewOnly
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

## Flujo recomendado de primer despliegue

1. ejecutar manualmente `refresh_data.ps1`
2. ejecutar manualmente `readiness_check.ps1`
3. ejecutar manualmente `run_editorial_day.ps1 -PreviewOnly`
4. ejecutar manualmente `editorial_release.ps1 -DryRun`
5. revisar:
   - `logs\cron_refresh.log`
   - `logs\cron_readiness.log`
   - `logs\cron_editorial.log`
   - `logs\cron_release.log`
   - `logs\cron_autoexport.log` si lanzas ese slot aparte
6. si todo es correcto, crear las tareas en Task Scheduler
7. mantener `Editorial Day` en `-PreviewOnly` durante los primeros dias si quieres validar sin persistencia
8. mantener `Editorial Release` en `-DryRun` hasta confirmar la politica de autoaprobacion
9. quitar `-PreviewOnly` y `-DryRun` cuando el comportamiento ya sea estable

## Editorial Release como panel operativo

El flujo recomendado pasa a ser:

1. `Refresh`
2. `Readiness`
3. `Editorial Day`
4. `Editorial Release`

`Editorial Release` hace internamente:

- `editorial_approval_policy`
- `editorial_quality_checks`
- `publication_dispatch`
- `typefully_autoexport`

Con eso, Typefully pasa a ser el panel real para piezas seguras.

Siguen en revision manual:

- `stat_narrative`
- `metric_narrative`
- `viral_story`

## Despliegue progresivo de autoexport

Archivo: `app/config/typefully_autoexport.json`

- `enabled=true` deja el pipeline listo para ejecutar en real
- `phase=1` limita la salida inicial a:
  - `match_result`
  - `standings`
  - `preview`
  - `ranking`
- `phase=2` anade:
  - `stat_narrative`
  - `metric_narrative`
- `phase=3` anade:
  - `viral_story`

Checklist recomendado:

1. mantener Task Scheduler con `editorial_release.ps1 -DryRun`
2. revisar `python -m app.pipelines.editorial_approval status`
3. revisar `python -m app.pipelines.typefully_autoexport status`
4. revisar `python -m app.pipelines.typefully_autoexport pending-capacity` si Typefully marca limite de plan
5. revisar `logs\cron_release.log`
6. revisar `logs\cron_autoexport.log` si mantienes ese slot aparte
7. cuando fase 1 sea estable, quitar `-DryRun`
8. subir a `phase=2` y repetir validacion
9. subir a `phase=3` solo cuando `viral_story` ya sea estable en revision editorial

Cada run deja una linea resumen parecida a esta en `logs\cron_autoexport.log`:

```text
[2026-03-20 11:20:01 +01:00] [INFO] AUTOEXPORT phase=1 scanned=10 eligible=10 exported=5 blocked=0 capacity_deferred=5 failed=0
```

El ultimo resumen estructurado queda tambien en `logs\typefully_autoexport_status.json`.

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
- `approve/reject`
- `publication_dispatch` de piezas sensibles
- `typefully_export` manual de cualquier pieza que falle `editorial_quality_checks`
- edicion final y programacion dentro de Typefully

## Limitaciones abiertas

- no hay rotacion automatica de logs en Windows; la limpieza es manual por ahora
- el lock evita duplicados del mismo slot, pero no sustituye la opcion `Do not start a new instance` de Task Scheduler
- el scheduler no resuelve logica editorial por hora; solo dispara scripts
