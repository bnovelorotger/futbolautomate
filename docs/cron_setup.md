# Automatizacion con cron

La automatizacion de uFutbolBalear es deliberadamente externa. `cron` no contiene logica editorial ni decide contenidos. Solo orquesta comandos ya existentes del backend.

## Principios

- `cron` solo ejecuta scripts shell ligeros
- los scripts shell solo invocan comandos de `app.pipelines.*`
- la logica editorial sigue en el backend
- no hay scheduler interno
- no hay autopublicacion
- la salida estructurada del release sigue siendo un paso explicito
- el JSON plano legacy queda desactivado salvo que lo reactives

## Scripts creados

Ruta: `scripts/cron/`

- `common.sh`
  - resuelve `PROJECT_ROOT`
  - carga entorno desde `.env.cron` y `.env`
  - crea `logs/` y `.locks/`
  - gestiona logs con timestamp
  - evita solapes con `flock` si esta disponible
- `refresh_data.sh`
  - ejecuta `competition_catalog seed --integrated-only --missing-only`
  - ejecuta refresh explicito de `matches` y `standings`
  - no ejecuta `run_daily`
  - no refresca noticias
- `readiness_check.sh`
  - ejecuta `competition_catalog status --integrated-only`
  - ejecuta `system_check editorial-readiness`
- `run_editorial_day.sh`
  - ejecuta `editorial_ops preview-day --date <fecha>`
  - ejecuta `editorial_ops run-daily --date <fecha>`
  - los viernes ya cubre `division_honor_mallorca` en `preview` y `featured_match_preview`
- `run_slot.sh`
  - envoltorio opcional
  - soporta `refresh`, `readiness` y `editorial-day`
  - no incluye `editorial-release`; ese cierre sigue siendo manual por ahora

## Variables y entorno

Los scripts cargan primero:

1. `.env.cron`
2. `.env`

Orden recomendado:

- usa `.env.cron` si quieres un fichero shell-safe para Linux/VPS
- deja `.env` para el backend si ya lo usas localmente

Variables minimas utiles para cron:

```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/futbol_balear
APP_TIMEZONE=Europe/Madrid
PYTHON_BIN=/srv/ufutbolbalear/.venv/bin/python
```

Notas:

- `PYTHON_BIN` puede definirse en `.env.cron` o en la propia `crontab`
- no metas secretos directamente en la `crontab` si puedes evitarlos
- `PREVIEW_ONLY=true` permite un primer despliegue seguro sin persistir borradores editoriales

## Logs y diagnostico

Los scripts escriben en `logs/`:

- `logs/cron_refresh.log`
- `logs/cron_readiness.log`
- `logs/cron_editorial.log`

Cada ejecucion deja:

- timestamp
- nombre del paso
- salida normal de los comandos
- fin correcta o error con `exit code`

Si falla un comando Python:

- el script termina con `exit != 0`
- el error queda reflejado en el log del slot

Si un slot ya se esta ejecutando:

- el lock evita una segunda ejecucion concurrente
- el script sale con warning y `exit 1`

## Por que `refresh_data.sh` no usa `run_daily`

La version final recomendada evita `python -m app.pipelines.run_daily` en cron porque `run_daily` hoy hace mas cosas de las necesarias para el refresh editorial:

- refresca todas las competiciones integradas del catalogo
- refresca noticias generales
- mezcla en un mismo paso la salud del refresh de competicion y la de feeds de noticias

Para un cron de produccion mas predecible conviene limitar el refresh a lo que el planner necesita hoy:

- `tercera_rfef_g11` -> `matches`, `standings`
- `segunda_rfef_g3_baleares` -> `matches`, `standings`
- `division_honor_mallorca` -> `matches`, `standings`

Eso reduce superficie de fallo y hace mas legible el log de refresh.

## Propuesta de crontab

Esta propuesta esta adaptada al estado real actual del sistema:

- competiciones operativas: `tercera_rfef_g11`, `segunda_rfef_g3_baleares`, `division_honor_mallorca`
- planner semanal operativo: lunes, miercoles, viernes y domingo
- juvenil/femenino: pendiente de integracion end-to-end
- sin `editorial_release` automatizado en cron por ahora

```cron
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
CRON_TZ=Europe/Madrid

PROJECT_ROOT=/srv/ufutbolbalear
PYTHON_BIN=/srv/ufutbolbalear/.venv/bin/python
APP_TIMEZONE=Europe/Madrid

# Lunes
35 08 * * 1 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/refresh_data.sh
45 08 * * 1 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/readiness_check.sh
00 09 * * 1 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/run_editorial_day.sh

# Miercoles
30 10 * * 3 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/refresh_data.sh
45 10 * * 3 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/readiness_check.sh
00 11 * * 3 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/run_editorial_day.sh

# Viernes
30 09 * * 5 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/refresh_data.sh
45 09 * * 5 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/readiness_check.sh
00 10 * * 5 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/run_editorial_day.sh

# Domingo
00 20 * * 0 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/refresh_data.sh
15 20 * * 0 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/readiness_check.sh
30 20 * * 0 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE scripts/cron/run_editorial_day.sh
```

Esta frecuencia es razonable hoy porque:

- solo se programa en los dias con reglas activas en el planner
- evita ruido innecesario en martes, jueves y sabado
- reduce carga y superficie de fallo en el primer despliegue
- sigue permitiendo aumentar frecuencia mas adelante si el medio necesita mas cadencia

## Tareas automatizadas

- seed/check de competiciones integradas antes del refresh
- refresh de datos de competiciones
- chequeo de readiness editorial
- generacion diaria planificada de `content_candidates`

## Tareas que siguen siendo manuales

- revisar la cola en `editorial_queue`
- `approve` / `reject`
- `publication_dispatch`
- ejecutar `python -m app.pipelines.editorial_release run --date <fecha>` para generar `exports/export_base.json`
- revisar el snapshot exportado y entregarlo al canal final
- ejecutar `python -m app.pipelines.export_base generate --date <fecha>` si necesitas regenerar `exports/export_base.json`
- revisar `export/legacy_export.json` solo si has activado `LEGACY_EXPORT_JSON_ENABLED=true`
- edicion final, ajuste fino y programacion en la herramienta externa que toque

## Checklist diaria recomendada

Despues de cada bloque de cron:

1. revisar `logs/cron_refresh.log`
2. revisar `logs/cron_readiness.log`
3. revisar `logs/cron_editorial.log`
4. comprobar `python -m app.pipelines.system_check editorial-readiness`
5. revisar borradores con `python -m app.pipelines.editorial_queue list --status draft --limit 40`

Para preparar salida manual:

1. elegir 3-5 piezas
2. revisar `editorial_queue show --id <ID>`
3. aprobar manualmente
4. despachar con `publication_dispatch dispatch --include-unscheduled`
5. validar con `python -m app.pipelines.editorial_release dry-run --date <fecha>`
6. generar `exports/export_base.json` con `python -m app.pipelines.editorial_release run --date <fecha>`
7. regenerar `exports/export_base.json` con `python -m app.pipelines.export_base generate --date <fecha>` si necesitas rehacer el snapshot
8. revisar `export/legacy_export.json` solo si has activado `LEGACY_EXPORT_JSON_ENABLED=true`

### Primer despliegue seguro

Si quieres activar cron sin persistir borradores todavia:

```cron
00 09 * * 1 cd $PROJECT_ROOT && PYTHON_BIN=$PYTHON_BIN APP_TIMEZONE=$APP_TIMEZONE PREVIEW_ONLY=true scripts/cron/run_editorial_day.sh
```

O manualmente:

```bash
PREVIEW_ONLY=true scripts/cron/run_editorial_day.sh 2026-03-17
```

## Checklist semanal recomendada

Cada lunes o tras cambios de competiciones:

1. revisar `competition_catalog status --integrated-only`
2. revisar si el planner semanal sigue alineado con las competiciones activas
3. revisar si hay slots sin uso real en cron
4. revisar si `division_honor_mallorca` sigue siendo apoyo regional o merece mas peso
5. revisar si juvenil/femenino ya puede integrarse end-to-end

## Despliegue minimo en Linux/VPS

1. crear el entorno virtual
2. instalar dependencias
3. definir `DATABASE_URL` y resto de variables en `.env.cron`
4. dar permisos de ejecucion:

```bash
chmod +x scripts/cron/*.sh
```

5. instalar la `crontab`
6. confirmar que `logs/` se crea automaticamente tras la primera ejecucion

## Ejemplo minimo de logrotate

Archivo recomendado: `/etc/logrotate.d/ufutbolbalear-cron`

```conf
/srv/ufutbolbalear/logs/cron_*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
    copytruncate
}
```

## Limitaciones abiertas

- no hay reintentos inteligentes; el diagnostico es por log y exit code
- no hay alertas por email, Slack o Telegram
- no hay rotacion de logs; conviene gestionarla con `logrotate`
- el planner no tiene slots propios por hora; el detalle horario sigue estando en la crontab
- domingo no automatiza clasificacion porque hoy la clasificacion esta planificada para el lunes
