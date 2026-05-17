# Runbook de Fase 3

Este runbook deja preparada la activacion controlada de `humanized_local` solo para `PREVIEW` y `VIRAL_STORY`, con rollback inmediato y sin tocar produccion a ciegas.

## Flags

No actives nada en produccion por defecto.

- `EDITORIAL_REWRITE_HUMANIZED_LOCAL_ENABLED=true`
  Habilita la capa de tono humanizado, pero no basta por si sola para entrar en fase 3.
- `EDITORIAL_PHASE3_ROLLOUT_ENABLED=true`
  Activa la compuerta fina de fase 3. Sin este flag, `PREVIEW` y `VIRAL_STORY` siguen en tono `legacy`.

Para rollback inmediato:

- `EDITORIAL_REWRITE_HUMANIZED_LOCAL_ENABLED=false`
- `EDITORIAL_PHASE3_ROLLOUT_ENABLED=false`

## Criterios explicitos de rollout

La politica vive en `app/config/editorial_rollout.json`.

Fase 3 solo permite:

- `PREVIEW`
  Requiere `featured_match` y prioridad minima `90`.
  Emite `editorial_voice={"mode":"preview_light","resource_id":"quin_partidas"}`.

- `VIRAL_STORY`
  Requiere prioridad minima `69`.
  Solo permite story types:
  - `win_streak`
  - `unbeaten_streak`
  - `hot_form`
  - `recent_top_scorer`
  - `best_attack`
  - `best_defense`

Quedan fuera en fase 3:

- `MATCH_RESULT`
- `RESULTS_ROUNDUP`
- `STANDINGS`
- `STANDINGS_ROUNDUP`
- `TOP_SCORER_UPDATE`
- `RACE_NARRATIVE`
- `MILESTONE_STORY`
- `FEATURED_MATCH_PREVIEW`

## Observabilidad

Con `LOG_JSON=true`, quedan trazas estructuradas en:

- `editorial_rollout_payload_prepared`
- `editorial_rewrite_started`
- `editorial_rewrite_completed`
- `editorial_rewrite_failed`
- `editorial_rewrite_failed_length`
- `editorial_quality_checked`

Campos utiles para fase 3:

- `candidate_id`
- `competition_slug`
- `content_type`
- `rewrite_mode`
- `applied_tone`
- `phase3_rollout_eligible`
- `phase3_rollout_reason`
- `editorial_voice_mode`
- `editorial_voice_resource_id`
- `quality_passed`
- `quality_error_count`
- `text_source`
- `rewrite_status`
- `rewrite_outcome`

Politica explicita de rewrite en produccion:

- si Groq devuelve JSON valido, usar rewrite real
- si Groq falla por `Failed to validate JSON`, `Failed to generate JSON` o `Rate limit reached`, usar fallback automatico a `base_text`
- registrar la salida con `rewrite_status` y `rewrite_outcome` para medir estabilidad y cuota

## Dry-run operativo

### 1. Dry-run de release

```bash
python -m app.pipelines.editorial_release dry-run --use-rewrite
```

### 2. Snapshot de fase 3 con quality checks recomputados

```bash
python -m app.pipelines.draft_temp sync --phase3-only --recompute-quality-checks --use-rewrite --output logs/draft_temp_phase3.json
```

### 3. Comando unico de readiness

```bash
python scripts/editorial_phase3_readiness.py --output logs/draft_temp_phase3.json
```

Ese comando:

- ejecuta `EditorialReleasePipelineService.run(..., dry_run=True)`
- genera snapshot de fase 3
- recomputa `quality_checks` en dry-run
- guarda `logs/draft_temp_phase3.json`

### 4. Smoke test del proveedor de rewrite

Usa el proveedor real en `dry-run`, sin persistir `rewritten_text`. Si faltan credenciales o modelo, devuelve un payload explicito con las variables pendientes.

La configuracion local por defecto queda preparada para `groq` con:

- `EDITORIAL_REWRITE_PROVIDER=groq`
- `EDITORIAL_REWRITE_API_URL=https://api.groq.com/openai/v1/chat/completions`
- `EDITORIAL_REWRITE_MODEL=openai/gpt-oss-20b`

```bash
python scripts/editorial_rewrite_provider_smoke.py --json
```

Para forzar un candidato concreto:

```bash
python scripts/editorial_rewrite_provider_smoke.py --candidate-id 255 --json
```

### 5. Ratio diario real vs fallback

Reporte diario desde base de datos:

```bash
python scripts/editorial_rewrite_daily_metrics.py --days 7 --output logs/editorial_rewrite_daily_metrics.json
```

Con rango explicito:

```bash
python scripts/editorial_rewrite_daily_metrics.py --start-date 2026-05-11 --end-date 2026-05-17
```

### 6. Lote piloto persistente

Antes de dejar correr el flujo normal del lunes, conviene persistir un lote corto y revisar el reparto real entre rewrite y fallback.

Secuencia recomendada:

1. seleccionar 5-10 candidatos elegibles de `PREVIEW` y `VIRAL_STORY`
2. ejecutar rewrite real con `overwrite=True`
3. recomputar `quality_checks` con `prefer_rewrite=True`
4. guardar un informe en `logs/`
5. al dia siguiente, revisar:
   - `real_ratio`
   - `fallback_ratio`
   - `failed_ratio`
   - reparto por `content_type`

Umbral operativo inicial sugerido:

- `failed_ratio` debe permanecer en `0`
- `fallback_ratio` es aceptable si evita caidas, pero si supera `0.50` durante varios dias seguidos conviene revisar cuota o proveedor
- `real_ratio` debe mejorar cuando la cuota diaria de Groq no este agotada

## Revision manual obligatoria

Revisar solo el subset elegible de fase 3 con esta checklist:

- no cambia datos
- no pierde `@handles`
- no pierde `#hashtags`
- no introduce tono forzado
- no mete localismo en piezas fuera de rollout

## Secuencia recomendada

1. activar flags solo en staging o entorno local controlado
2. ejecutar `scripts/editorial_phase3_readiness.py`
3. revisar `logs/draft_temp_phase3.json`
4. si todo queda limpio, mantener activacion limitada a `PREVIEW` y `VIRAL_STORY`
5. no abrir fase 4 hasta recomputar baseline de `RACE_NARRATIVE` y `MILESTONE_STORY`

---

## Checklist de revision del lunes (fase 3 en produccion)

Ejecutar el dia siguiente al primer lunes con fase 3 activa.

### 1. Metricas de rewrite (automatico)

```bash
python scripts/editorial_rewrite_daily_metrics.py --days 1 --output logs/editorial_rewrite_daily_metrics.json
```

Valores de referencia:

| Metrica | Umbral aceptable |
|---------|-----------------|
| `real_ratio` | > 0.5 (idealmente > 0.7) |
| `fallback_ratio` | < 0.5; si supera 0.5 revisar cuota Groq |
| `failed_ratio` | debe ser 0; cualquier valor > 0 es alerta |

Si `failed_ratio > 0`: revisar logs con `LOG_JSON=true` buscando `editorial_rewrite_failed`.

### 2. Muestra manual de piezas (10-15)

```bash
python scripts/editorial_phase3_readiness.py --output logs/draft_temp_phase3.json
```

Abrir `logs/draft_temp_phase3.json` y revisar 10-15 piezas de tipo `PREVIEW` y `VIRAL_STORY`.

Para cada pieza comprobar:

- [ ] El texto es coherente y no tiene datos inventados
- [ ] Los `@handles` de equipos estan presentes y son correctos
- [ ] Los `#hashtags` (#FutbolBalear, etc.) se conservan
- [ ] El tono es local y natural, no forzado ni generico
- [ ] No hay mezcla de idiomas (castellano/catalan) inesperada
- [ ] La longitud no supera el limite de X (280 caracteres por tweet)

### 3. Piezas varadas (stranded)

```bash
python -m app.pipelines.x_publish show-all-unpublished
```

Si hay piezas con `external_publication_ref=None` y `published_at` > 1 dia:

```bash
python -m app.pipelines.x_publish browser-pending --bypass-schedule --dry-run
# Si el dry-run muestra las piezas correctas:
python -m app.pipelines.x_publish browser-pending --bypass-schedule
```

### 4. Logs de release

Revisar `logs/cron_release.log` buscando:

- `editorial_rewrite_failed` — fallos de rewrite
- `editorial_rewrite_failed_length` — textos rechazados por longitud tras rewrite
- `XBrowserSessionError` — sesion de browser caducada (ejecutar `browser-auth-capture`)
- `SelectorDriftError` — cambio de estructura HTML en scraper

### 5. Decision de continuidad

- Todo verde (`failed_ratio=0`, muestra manual OK): dejar correr fase 3 sin cambios.
- `fallback_ratio > 0.5` durante 2+ dias: revisar cuota Groq o cambiar `EDITORIAL_REWRITE_PROVIDER`.
- Cualquier `failed_ratio > 0`: rollback inmediato con `EDITORIAL_PHASE3_ROLLOUT_ENABLED=false`.
