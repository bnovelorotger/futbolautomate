# Runbook de Telegram

Este documento fija el contrato operativo para las notificaciones de Telegram del repo. Cubre cuatro flujos:

- agenda editorial de la jornada (`day plan`)
- aviso puntual por cada `post publicado`
- digest diario editorial (`digest`)
- alertas de error de tarea (`error`) cuando una tarea operativa falla

`inicio` y `fin` de tarea ya no forman parte del carril normal de produccion. Siguen existiendo en `TelegramEventNotifier`, pero quedan desactivados por defecto.

## Mensajes existentes

### 1. Error de tarea

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

### 2. Digest diario

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

### 3. Agenda editorial del dia

Emisor esperado: `EditorialDayPlanService`.

Contenido minimo recomendado:

- fecha objetivo
- calendario del dia (`day_key`, `publish_slots`, tipos programados)
- total de piezas previstas
- estado actual (`published`, `approved`, `draft`, `rejected`)
- listado corto de piezas del dia

Titulo esperado:

```text
futbolbalear - agenda editorial
```

### 4. Aviso de post publicado

Emisor esperado: `TelegramPublicationNotifier.publication_succeeded()`.

Contenido minimo recomendado:

- `id`
- `type`
- `competition`
- `reference_date`
- `published_at`
- `text_source`
- `excerpt`

Titulo esperado:

```text
futbolbalear - post publicado
```

## Tareas que deben notificar

Las notificaciones de evento no requieren una tarea programada aparte. Se emiten desde las tareas ya existentes del scheduler cuando el wrapper de esa tarea llama al notifier.

Scope operativo recomendado:

- `editorial_release`
- `check_browser_session`
- `editorial_day_plan`
- `editorial_daily_digest`
- `x_browser_publication_service` para los avisos de `post publicado`

Criterio de ruido:

- `inicio` y `fin` desactivados por defecto
- `error` para cualquier tarea que corte la cadena operativa o deje el dia sin salida editorial
- la `agenda editorial` debe salir una sola vez por la manana
- el aviso de `post publicado` debe salir una vez por publicacion correcta
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

- hora recomendada: `08:00`
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

## Flags operativos

Variables relevantes en `Settings`:

- `telegram_task_start_finish_enabled=false`
- `telegram_task_error_enabled=true`
- `telegram_publication_notifications_enabled=true`

Lectura operativa:

- produccion normal: agenda + post publicado + digest + alertas de error
- no enviar `inicio` y `fin` salvo que se activen explicitamente para diagnostico

## Cobertura actual en tests

Cubierto en este repo:

- `TelegramNotificationService`
- `TelegramEventNotifier`
- `TelegramPublicationNotifier`
- `EditorialDayPlanService`
- `EditorialDailyDigestService`
- CLI manual `telegram_notify setup`
- CLI manual `telegram_notify test`
- pipeline/CLI de agenda editorial
- pipeline/CLI de digest diario
