# Evaluacion Offline y Rollout de `editorial_rewriter`

## Alcance

Este baseline cubre solo el workstream de evaluacion de reescritura editorial y no toca runtime de produccion.

- Corpus separado en dos grupos:
  - `data_pure`: tipos `strict_data` donde la prioridad es preservar estructura y dato exacto.
  - `humanizable`: tipos `humanized_local` donde tiene sentido medir mejora de tono sin relajar invariantes.
- Comparativa fija entre 3 variantes:
  - `draft`
  - `current_rewrite`
  - `humanized_local`
- Metricas automatizadas:
  - tasa de fallo de `editorial_quality_checks`
  - longitud media
  - preservacion de datos esperados
  - preservacion exacta de `@handles`
  - preservacion exacta de `#hashtags`

El corpus vive en `tests/fixtures/editorial_rewrite_eval_samples.json` y se ejecuta con `scripts/editorial_rewrite_offline_eval.py`.

## Como ejecutar

Con salida legible:

```bash
python scripts/editorial_rewrite_offline_eval.py
```

Con salida JSON:

```bash
python scripts/editorial_rewrite_offline_eval.py --json
```

Persistiendo snapshot del informe:

```bash
python scripts/editorial_rewrite_offline_eval.py --json --output logs/editorial_rewrite_eval.json
```

## Que automatiza el baseline

El script monta una BD SQLite en memoria reutilizando la infraestructura de tests y las competiciones semilla ya existentes. Sobre esa base:

1. carga 20 muestras curadas: 10 `data_pure` y 10 `humanizable`
2. inserta cada muestra como `ContentCandidate`
3. ejecuta `EditorialQualityChecksService` en las 3 variantes
4. calcula preservacion de datos, handles y hashtags a partir de expectativas declaradas en el fixture
5. resume por grupo, por tipo y por subset de rollout:
   - fase 3: `PREVIEW` + `VIRAL_STORY`
   - fase 4: `RACE_NARRATIVE` + `MILESTONE_STORY`

## Limitaciones y parte manual

La comparativa textual de `current_rewrite` y `humanized_local` usa variantes curadas en fixture. Eso permite repetir la evaluacion sin depender del proveedor LLM, pero no sustituye una captura real de outputs de produccion.

Procedimiento manual recomendado cuando haya que refrescar el baseline con outputs reales:

1. sacar una muestra cerrada de candidatos reales por tipo desde staging o snapshot local
2. ejecutar `editorial_rewrite` con el modo actual y guardar `rewritten_text`
3. repetir con `editorial_rewrite_humanized_local_enabled=true`
4. reemplazar solo los campos `variants.current_rewrite` y `variants.humanized_local` del fixture
5. volver a correr `python scripts/editorial_rewrite_offline_eval.py --json --output logs/editorial_rewrite_eval.json`

La evaluacion de “tono mas natural” sigue siendo manual. El criterio sugerido es revisar diffs solo en el subset candidato a rollout y marcar:

- suena menos robotico
- no añade contexto no medido
- no rompe handles, hashtags ni cifras
- no pierde claridad de lectura

## Criterios de exito

### Gate global

- `current_rewrite` no puede empeorar frente a `draft` en fallo de quality checks.
- `humanized_local` no puede activarse en un tipo si baja la preservacion exacta de handles o hashtags por debajo de `1.0`.
- `humanized_local` no puede activarse en un tipo si baja la preservacion media de datos por debajo de `0.98`.

### Gate fase 3

Solo aplica a `PREVIEW` y `VIRAL_STORY`.

- `qc_failed_count == 0`
- `handle_exact_match_rate == 1.0`
- `hashtag_exact_match_rate == 1.0`
- `average_data_preservation_rate == 1.0`
- revision manual sin hallazgos de “hype”, inventiva o perdida de contexto clave

### Gate fase 4

Aplica a `RACE_NARRATIVE` y `MILESTONE_STORY`.

- repetir corpus con mas muestra real antes de activar
- exigir los mismos gates de preservacion que en fase 3
- anadir revision manual centrada en cifras de margen, jornadas restantes y hitos numericos

## Rollout propuesto

### Fase 1: offline only

- ejecutar solo `scripts/editorial_rewrite_offline_eval.py`
- no cambiar ningun flag de produccion
- objetivo: validar baseline y detectar regresiones obvias en `humanized_local`
- rollback: no aplica, no hay activacion

### Fase 2: dry-run con snapshot

- correr el pipeline editorial normal en `dry-run`
- capturar snapshot estructurado o `draft_temp`
- contrastar candidatos reales con el corpus offline
- objetivo: verificar que el mix real de textos no rompe los gates del baseline
- rollback: volver a `dry-run` sin publicar ni persistir rewrites nuevas

### Fase 3: activacion solo para `VIRAL_STORY` y `PREVIEW`

- mantener el resto de tipos en comportamiento actual
- activar `humanized_local` solo si el subset de fase 3 sigue en verde
- muestrear manualmente snapshots diarios durante varios dias
- rollback:
  - desactivar `editorial_rewrite_humanized_local_enabled`
  - volver a `current_rewrite`
  - no ampliar a otros tipos hasta recomputar baseline

### Fase 4: evaluar `RACE_NARRATIVE` y `MILESTONE_STORY`

- no activar directamente
- ampliar corpus y repetir medicion
- revisar especialmente perdida de cifras cortas: `1 punto`, `2 puntos`, `4 jornadas`, `12 partidos`, `20 goles`
- rollback: mantenerlos fuera del rollout si aparece cualquier degradacion en preservacion

## Recomendacion

Con este baseline, la salida prudente es:

- mantener `data_pure` fuera de cualquier rollout de humanizacion
- usar `dry-run` como paso intermedio obligatorio
- no pasar de fase 3 a fase 4 hasta recomputar baseline con muestra real adicional
