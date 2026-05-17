# Backlog Editorial Futuro

Este documento recoge decisiones aplazadas y lineas de trabajo futuras para no perder contexto. No implica activacion inmediata ni cambio de scope del rollout actual.

## Estado actual

El proyecto deja operativo hoy:

- rollout de fase 3 solo para `PREVIEW` y `VIRAL_STORY`
- provider de rewrite con `groq`
- fallback automatico a `base_text`
- metricas `real_ratio`, `fallback_ratio`, `failed_ratio`
- alertas operativas basicas

El foco actual sigue siendo:

- estabilidad de fase 3
- observabilidad diaria
- operacion segura sobre `futbolme`

## Fase 4 aplazada

Tipos fuera del rollout activo:

- `RACE_NARRATIVE`
- `MILESTONE_STORY`
- `FEATURED_MATCH_PREVIEW`

### Que significa recomputar baseline real para fase 4

Antes de permitir humanizacion en `RACE_NARRATIVE` o `MILESTONE_STORY`, hay que montar evidencia real sobre muestra de produccion o snapshot local realista.

Secuencia prevista:

1. recoger una muestra real de candidatos de ambos tipos durante varios dias
2. guardar para cada muestra:
   - `text_draft`
   - `formatted_text`
   - `rewritten_text` o `dry-run`
   - `payload_json`
3. comparar:
   - borrador base
   - rewrite actual
   - variante `humanized_local`
4. revisar manualmente preservacion exacta de:
   - equipos
   - posiciones objetivo
   - margen de puntos
   - jornadas restantes
   - hitos numericos
5. decidir si esos tipos pueden humanizarse o si deben seguir en `strict_data`

Razon del aplazamiento:

- en estos tipos el riesgo principal es semantico, no solo de longitud o hashtags
- un rewrite incorrecto puede distorsionar narrativa competitiva o hitos estadisticos

## Metricas post-publicacion en X

Esto queda fuera por ahora.

Motivo:

- no hay acceso operativo a API de X para analitica
- no se quiere scraping de X por riesgo y fragilidad

Si algun dia se retoma, la via prudente seria:

- export manual de analytics
- ingesta local de CSV
- cruce con `content_candidates`

No es prioridad del scope actual.

## Automatizacion diaria por Telegram

Esto si es una linea recomendada a corto plazo.

### Infraestructura ya existente

El repo ya tiene base para notificaciones Telegram:

- `app/services/telegram_notification_service.py`
- `app/pipelines/pipeline_summary.py`
- `app/services/pipeline_summary_service.py`
- `scripts/windows/daily_summary.ps1`

Hoy Telegram sirve para alertas operativas basicas cuando existen incidencias. No envia aun un resumen diario rico aunque no haya alertas.

### Objetivo futuro recomendado

Enviar por Telegram un resumen de cierre del dia con:

- posts publicados
- pendientes de dispatch
- errores de publicacion
- `real_ratio`
- `fallback_ratio`
- `failed_ratio`
- alertas activas
- top de bloqueos o rechazos si aplica

### Scope recomendado para una futura implementacion

1. ampliar el resumen diario actual para incluir metricas de rewrite
2. separar:
   - resumen diario siempre enviado
   - alertas puntuales solo cuando haya incidencias
3. dejarlo programable por scheduler Windows
4. mantener salida compacta para Telegram

### Criterio de aceptacion futuro

- un mensaje diario siempre llega aunque no haya alertas
- un mensaje de alerta adicional solo sale en incidencias reales
- el resumen incluye ratios de rewrite y estado de publicacion
- no depende de scraping de X

## Expansion de canales

### BlueSky

BlueSky queda diferido.

Motivo:

- hoy no existe integracion real en el repo
- seria basicamente duplicar el texto de X en otro canal
- aporta menos valor inmediato que mejorar observabilidad o producto long-form

Si algun dia se retoma, necesitara:

- credenciales y autenticacion del canal
- cliente/publicador propio
- trazabilidad persistida
- scheduling o dispatch integrado

### Recomendacion: priorizar Substack antes que BlueSky

Si el siguiente canal nuevo debe aportar algo distinto, la recomendacion es priorizar Substack.

Motivos:

- el proyecto ya genera datos estructurados y resumenes que encajan mejor en formato semanal o long-form
- Substack monetiza y fideliza mejor que duplicar micro-posts en otra red
- la base editorial actual puede alimentar una newsletter con poco salto conceptual

### Linea futura para Substack

La ruta mas natural seria:

1. partir de `export_base.json` o del resumen editorial estructurado
2. construir un exportador Markdown
3. generar una newsletter semanal automatizable
4. revisar manualmente antes de publicar en una fase inicial

Contenido candidato:

- clasificaciones
- goleadores
- narrativas metricas
- rachas destacadas
- agenda del fin de semana

### Por que Substack antes que BlueSky

- mas diferenciacion de producto
- mejor encaje con la capa data-oriented
- mas recorrido futuro de negocio o suscripcion
- menos dependencia de ritmo diario de red social

## Fuentes de datos

No se abre ahora ningun frente nuevo de scraping o APIs.

Decision vigente:

- se sigue trabajando con `futbolme`
- no se abre ahora trabajo nuevo de cobertura de fuentes o competiciones

Razon:

- el cuello de botella actual no es la fuente
- el valor inmediato esta en observabilidad, operacion y formato editorial
