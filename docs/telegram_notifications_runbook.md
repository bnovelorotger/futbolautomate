# Runbook de Telegram

Este documento fija el contrato operativo para las notificaciones de Telegram del repo. Cubre tres flujos:

- eventos de tarea (`inicio`, `fin`, `error`)
- agenda editorial de la jornada (`day plan`)
- digest diario editorial (`digest`)

Si tu branch todavia no incluye `EditorialDailyDigestService` o su pipeline/CLI, toma este documento como la referencia de operacion y de naming que debe respetar el codigo productivo cuando entre.

## Mensajes existentes

### 1. Inicio de tarea

Emisor esperado: `TelegramEventNotifier.task_started()`

Campos minimos:

- `task`
- `status`

Campos opcionales:

- `mode`
- `started_at`
- metricas resumen (`summary_metrics`)

Titulo esperado:

```text
futbolbalear - inicio tarea
```

### 2. Fin de tarea

Emisor esperado: `TelegramEventNotifier.task_finished()`

Campos minimos:

- `task`
- `status`

Campos opcionales:

- `mode`
- `started_at`
- `duration`
- metricas resumen

Titulo esperado:

```text
futbolbalear - tarea completada
```

### 3. Error de tarea

Emisor esperado: `TelegramEventNotifier.task_failed()`

Campos minimos:

- `task`
- `status`

Campos opcionales:

- `mode`
- `started_at`
- `duration`
- `reason`
- metricas resumen

Titulo esperado:

```text
futbolbalear - tarea con error
```

### 4. Digest diario

Emisor esperado: `EditorialDailyDigestService` cuando el servicio este disponible.

Contenido minimo recomendado:

- fecha de referencia
- volumen editorial del dia
- resumen de publicacion
- ratios de rewrite (`real`, `fallback`, `failed`)
- incidencias o alertas abiertas

Titulo esperado:

```text
futbolbalear - digest diario
```

### 5. Agenda editorial del dia

Emisor esperado: `EditorialDayPlanService`.

Contenido minimo recomendado:

- fecha objetivo
- calendario del dia (`day_key`, `publish_after`, tipos programados)
- total de piezas previstas
- estado actual (`published`, `approved`, `draft`, `rejected`)
- listado corto de piezas del dia

Titulo esperado:

```text
futbolbalear - agenda editorial
```

## Tareas que deben notificar

Las notificaciones de evento no requieren una tarea programada aparte. Se emiten desde las tareas ya existentes del scheduler cuando el wrapper de esa tarea llama al notifier.

Scope operativo recomendado:

- `refresh_data`
- `readiness_check`
- `run_editorial_day`
- `editorial_release`
- `auto_publish_browser`
- `check_browser_session`
- `editorial_day_plan`
- `editorial_daily_digest` cuando exista el pipeline diario de digest

Criterio de ruido:

- `inicio` y `fin` para tareas largas o criticas
- `error` para cualquier tarea que corte la cadena operativa o deje el dia sin salida editorial
- la `agenda editorial` debe salir una sola vez por la manana
- el `digest` debe salir una sola vez por dia

## Prueba manual de Telegram

### 1. Configurar credenciales

Variables necesarias:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### 2. Descubrir `chat_id` si aun no lo tienes

Primero envia cualquier mensaje al bot desde la app de Telegram. Luego ejecuta:

```powershell
python -m app.pipelines.runner telegram_notify setup
```

Salida esperada:

```text
Chat ID encontrado: 123456789
```

### 3. Enviar un mensaje de prueba

```powershell
python -m app.pipelines.runner telegram_notify test "futbolbalear test telegram"
```

Salida esperada:

```text
Mensaje enviado correctamente.
```

Si falla:

- revisar `TELEGRAM_BOT_TOKEN`
- revisar `TELEGRAM_CHAT_ID`
- verificar que el bot ya recibio al menos un mensaje del chat destino

## Programacion diaria recomendada

### Agenda editorial

- hora recomendada: `09:00`
- tarea scheduler: `futbol_editorial_day_plan`
- script: `scripts/windows/editorial_day_plan.ps1 -SendTelegram`

### Digest diario

Programarlo como tarea separada en Windows Task Scheduler.

Reglas operativas:

- una ejecucion al dia
- siempre despues del ultimo `editorial_release` y del posible retry de publicacion del dia
- evitar solape con lotes de publicacion largos

Ventana recomendada:

- programar el digest con un margen de 15 a 30 minutos respecto al ultimo slot real de release/publicacion del dia

Naming recomendado:

- tarea scheduler: `futbol_editorial_digest`
- script: `scripts/windows/editorial_daily_digest.ps1 -SendTelegram`
- log: `logs\\editorial_daily_digest.log`

Wrapper recomendado:

- seguir el patron de `scripts/windows/common.ps1`
- cargar `.env`
- escribir log con timestamp
- usar lock file

## Significado de ratios `real`, `fallback`, `failed`

Fuente esperada: `EditorialRewriteMetricsService.daily_outcome_report()`.

### `real_ratio`

Porcentaje de rewrites resueltos con salida real del proveedor.

Estados asociados hoy:

- `rewritten`
- `dry_run`

Lectura operativa:

- alto es bueno
- indica que el proveedor esta respondiendo y la salida se pudo usar

### `fallback_ratio`

Porcentaje de rewrites resueltos con fallback a `base_text` por un error recuperable del proveedor.

Estados asociados hoy:

- `rewritten_fallback_base_text`
- `dry_run_fallback_base_text`

Lectura operativa:

- no rompe el pipeline
- si sube demasiado, revisar cuota, rate limit o estabilidad del proveedor

### `failed_ratio`

Porcentaje de rewrites que terminaron en fallo duro y no pudieron resolverse ni con fallback.

Estados asociados hoy:

- `failed`

Lectura operativa:

- debe tender a `0`
- cualquier valor mayor que `0` merece revision de logs y del proveedor

## Cobertura actual en tests

Cubierto en este repo:

- `TelegramNotificationService`
- `TelegramEventNotifier`
- `EditorialDayPlanService`
- `EditorialDailyDigestService`
- CLI manual `telegram_notify setup`
- CLI manual `telegram_notify test`
- pipeline/CLI de agenda editorial
- pipeline/CLI de digest diario
