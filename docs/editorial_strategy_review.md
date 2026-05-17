# Revision de Estrategia Editorial y Humanizacion

## Objetivo

El proyecto tiene dos metas que deben convivir sin degradarse entre si:

1. precision absoluta en datos, resultados y clasificaciones
2. crecimiento de audiencia y senal de marca en X mediante una voz menos robotica

La arquitectura nueva separa esas dos preocupaciones. La personalidad entra solo en el envoltorio, nunca en el dato.

## Decisiones ya implementadas

### 1. Dos modos editoriales explicitos

- `strict_data`
- `humanized_local`

`strict_data` protege piezas donde la claridad y la exactitud mandan:

- `MATCH_RESULT`
- `RESULTS_ROUNDUP`
- `STANDINGS`
- `STANDINGS_ROUNDUP`
- `TOP_SCORER_UPDATE`

`humanized_local` queda limitado por rollout a piezas donde una capa ligera de voz aporta mas que el tono teletipo:

- `PREVIEW`
- `VIRAL_STORY`

Otros tipos como `RACE_NARRATIVE`, `MILESTONE_STORY` o `FEATURED_MATCH_PREVIEW` siguen fuera del rollout activo.

### 2. Guardrails duros

La reescritura nunca puede:

- alterar datos
- inventar `@handles`
- inventar `#hashtags`
- cambiar nombres de equipos
- cambiar numeros del payload
- romper el maximo de caracteres

Si el proveedor LLM falla, el sistema vuelve automaticamente a `base_text`.

### 3. Voz local configurable y conservadora

La voz local no esta hardcodeada como regla global. Vive en configuracion y solo puede aplicarse si coinciden:

- el modo editorial
- el tipo de contenido
- la compuerta de rollout
- el flag global de humanizacion

La version inicial usa una allowlist pequena y medible. El objetivo es sonar local sin caer en caricatura.

### 4. Rollout reversible

La fase 3 solo se activa para `PREVIEW` y `VIRAL_STORY` y exige dos flags:

- `EDITORIAL_REWRITE_HUMANIZED_LOCAL_ENABLED=true`
- `EDITORIAL_PHASE3_ROLLOUT_ENABLED=true`

Rollback:

- `EDITORIAL_REWRITE_HUMANIZED_LOCAL_ENABLED=false`
- `EDITORIAL_PHASE3_ROLLOUT_ENABLED=false`

## Politica de proveedor

El proveedor operativo actual es `groq`.

Politica de produccion ya implementada:

- si Groq devuelve JSON valido, se usa rewrite real
- si Groq falla por JSON invalido o `rate limit`, se usa fallback automatico a `base_text`
- el sistema registra `rewrite_status` y `rewrite_outcome` para medir estabilidad y cuota

Esto permite mantener el flujo operativo aunque la capa LLM falle o se quede sin cuota diaria.

## Observabilidad y control

La operativa diaria ya puede medir:

- ratio `real vs fallback`
- `failed_ratio`
- desglose por `content_type`
- elegibilidad de rollout
- motivos de bloqueo de quality checks

Documentos de referencia:

- `docs/editorial_phase3_runbook.md`
- `docs/editorial_rewrite_rollout_eval.md`

## Recomendacion operativa

La estrategia correcta no es "humanizar todo", sino aplicar personalidad donde aporta y dejar limpio el nucleo de datos.

Orden de confianza actual:

1. mantener `strict_data` fuera de cualquier localismo
2. operar fase 3 solo con `PREVIEW` y `VIRAL_STORY`
3. revisar ratios diarios antes de abrir mas tipos
4. no abrir fase 4 hasta recomputar baseline real para `RACE_NARRATIVE` y `MILESTONE_STORY`
