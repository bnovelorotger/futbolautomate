# Automatizacion Windows con PowerShell y Task Scheduler

Windows es el entorno principal actual de operacion de uFutbolBalear. La automatizacion se hace con PowerShell y el Programador de tareas de Windows, sin WSL y sin mover logica al backend.

## Principios

- PowerShell es la capa externa de orquestacion
- toda la logica sigue en `app.pipelines.*`
- no hay scheduler interno
- no hay autopublicacion en X
- `editorial_release` deja el handoff final en `export/export_base.json`
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
  - el pipeline interno hace `quality_checks -> autoapprove -> dispatch -> export_json`
  - en produccion v1 solo exporta automaticamente al JSON local:
    - `results_roundup`
    - `standings_roundup`
    - `preview`
    - `ranking`
- `run_slot.ps1`
  - wrapper opcional para `refresh`, `readiness`, `editorial-day` y `editorial-release`

## Variables y entorno

Orden de carga:

1. `.env`
2. `.env.windows`

Variables utiles:

```powershell
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/futbol_balear
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

La frontera automatica real vive en codigo:

- `EditorialApprovalPolicyService` solo autoaprueba `results_roundup`, `standings_roundup`, `preview` y `ranking`
- `EditorialCandidateWindowService` limita la ventana temporal del release
- `ExportJsonService` solo exporta piezas `published` sin `external_publication_ref`
- el artefacto final se escribe en `export/export_base.json`

## Ejecucion manual exacta

Desde PowerShell en la raiz del proyecto:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\refresh_data.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\readiness_check.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\run_editorial_day.ps1" -TargetDate 2026-03-17
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\editorial_release.ps1" -TargetDate 2026-03-17 -DryRun
python -m app.pipelines.editorial_quality_checks dry-run --date 2026-03-17
python -m app.pipelines.editorial_approval dry-run --date 2026-03-17
python -m app.pipelines.editorial_release dry-run --date 2026-03-17
python -m app.pipelines.editorial_release run --date 2026-03-17
python -m app.pipelines.system_check editorial-readiness
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
6. revisar `python -m app.pipelines.system_check editorial-readiness`
7. revisar `export/export_base.json` tras un `editorial_release run`
8. si todo es correcto, crear las tareas en Task Scheduler
9. quitar `-PreviewOnly` y `-DryRun` cuando el comportamiento ya sea estable

## Editorial Release como cierre operativo v1

El flujo recomendado es:

1. `Refresh`
2. `Readiness`
3. `Editorial Day`
4. `Editorial Release`

`Editorial Release` hace internamente:

- `editorial_quality_checks`
- `editorial_approval_policy`
- `publication_dispatch`
- `export_json_service`

Con eso, `export/export_base.json` pasa a ser el handoff estable para las piezas seguras de produccion v1.

## Export JSON local

`editorial_release run` genera `export/export_base.json` con una lista estable para consumo externo:

- aplica prioridad de texto via `EditorialTextSelectorService`
- deduplica piezas ya incluidas en el mismo payload
- bloquea series parciales de `results_roundup` y `standings_roundup`
- deja trazabilidad con `export_json_count`, `export_json_path` y `blocked_partition_series`

El consumo y publicacion final del JSON siguen siendo externos al scheduler.


## Tareas que siguen siendo manuales

- revisar drafts en `editorial_queue`
- `approve/reject` de piezas fuera de la frontera v1
- `publication_dispatch` de piezas sensibles
- revisar `export/export_base.json` antes de entregarlo al canal final
- edicion final y programacion en la herramienta externa que toque

## Limitaciones abiertas

- no hay rotacion automatica de logs en Windows; la limpieza es manual por ahora
- el lock evita duplicados del mismo slot, pero no sustituye la opcion `Do not start a new instance` de Task Scheduler
- el scheduler no resuelve logica editorial por hora; solo dispara scripts
