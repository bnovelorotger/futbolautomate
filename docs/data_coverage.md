# Cobertura de datos editoriales

Documento operativo del subsistema de cobertura: garantiza que el pipeline
solo genere y autorice contenido cuando los datos estadisticos de base
estan completos.

## Por que existe

El planner editorial inserta `draft`s a partir de lo que dicta la parrilla
(`editorial_schedule.json`). Pero un draft sin resultados o sin
clasificacion completa produce piezas vacias o, peor, falsas. El subsistema
de cobertura corta el flujo antes de publicar.

Dos servicios complementarios:

| Servicio | Que comprueba | Tabla |
|----------|---------------|-------|
| `StatCoverageService` | Cobertura agregada por competicion: ratio de partidos con resultado y filas de clasificacion completas + frescura del scrape | (sin tabla propia: lee de `matches`, `standings`, `scraper_runs`) |
| `MatchEventEnricherService` + `MatchDataCoverageRepository` | Cobertura partido a partido para goleadores y halftime | `match_data_coverage` (mig `20260524_0019`) + `matches.scorer_status` (mig `20260523_0018`) |

## Estados (`DataCoverageStatus`)

| Estado | Significado |
|--------|-------------|
| `PENDING` | Aun no se ha intentado comprobar |
| `COVERED` | Datos completos por encima del umbral |
| `PARTIAL` | Hay datos parciales (algunos resultados / algunas filas) |
| `NO_DATA` | No hay nada que comprobar todavia |
| `SOURCE_MISSING` | Se intento y no llego nada |
| `STALE` | Cobertura completa pero scrape mas antiguo que `STANDINGS_MAX_STALENESS_DAYS` (7 dias) |
| `ERROR` | El enriquecedor fallo de forma controlada |

`DataCoverageType` enumera los tipos: `RESULT`, `STANDINGS`, `SCORERS`,
`HALFTIME`.

## Umbrales aplicados

`app/services/stat_coverage.py`:

- `RESULT_COVERAGE_MIN_RATIO = 0.95` — al menos el 95 % de partidos
  `finished` deben tener `home_score`/`away_score`.
- `STANDINGS_COVERAGE_MIN_RATIO = 1.0` — todas las filas con
  `position`, `points`, `goals_for`, `goals_against`.
- `STANDINGS_MAX_STALENESS_DAYS = 7` — incluso con cobertura plena, una
  tabla mas vieja que 7 dias se reporta `STALE`.

`app/services/top_scorer_tracker.py`:

- `MIN_TOP_SCORER_COVERAGE_RATIO` — usado por el planner y los quality
  checks para abortar `top_scorer_update` si la cobertura de goleadores
  por partido cae por debajo del umbral.

## Como bloquea el pipeline

1. `EditorialQualityChecksService` invoca
   `StatCoverageService.coverage_errors_for_candidate(candidate, source_payload)`
   en cada chequeo. Si la cobertura no llega, anade errores tipo:
   - `result_coverage_no_finished_matches`
   - `result_coverage_ratio<0.95`
   - `standings_coverage_rows_missing`
   - `standings_coverage_ratio<1`
   - `standings_coverage_stale>7d`
2. Esos errores quedan en `content_candidates.quality_errors` y la pieza
   no es autoaprobada.
3. Para `top_scorer_update` se anade tambien
   `top_scorer_coverage_ratio<X`, calculado contra
   `scorer_covered_matches_count / finished_matches_count`.

El payload de cada candidata transporta los campos relevantes
(`finished_matches_count`, `scorer_covered_matches_count`,
`scorer_coverage_ratio`) para que el chequeo no tenga que recomputarlos.

## Estado de goleadores por partido (`matches.scorer_status`)

Cada partido tiene un estado independiente:

- `PENDING` — aun no intentado.
- `COVERED` — eventos de gol completos (`has_scorers=true` o
  enriquecedor cerro la ventana).
- `NO_GOALS` — partido finalizado 0-0; no hay nada que ingerir.
- `MISSING_SOURCE` — la fuente respondio pero sin datos esperados.
- `PARTIAL` — eventos parciales (faltan goles segun marcador).
- `ERROR` — fallo controlado del scrape.

`MatchEventEnricherService` setea `scorer_status` y `scorer_checked_at`
en cada intento y refleja el resultado en `match_data_coverage` (una
fila por `(match_id, data_type)`).

El repositorio `MatchRepository._preserve_scorer_enrichment` evita que
un reingest sobrescriba los enriquecimientos: si la fuente upstream
devuelve `scorer_status=pending` o `has_scorers=false`, se preserva el
valor previo.

## CLI

### Informe agregado por competicion

```bash
# Legible
python -m app.pipelines.runner stat_coverage report --season 2025-26

# JSON
python -m app.pipelines.runner stat_coverage report --competition tercera_rfef_g11 --json
```

### Cobertura de goleadores

```bash
# Resumen por competicion
python -m app.pipelines.runner match_events coverage-report --season 2025-26

# Reintento de partidos pendientes/parciales
python -m app.pipelines.runner match_events enrich-pending \
    --competition tercera_rfef_g11 --season 2025-26 --limit 250

# Forzar reintento de partidos en estado ERROR
python -m app.pipelines.runner match_events enrich-pending \
    --competition tercera_rfef_g11 --include-errors --limit 100
```

## Backfills programados (Windows Task Scheduler)

Dos scripts batch dejan la cobertura en verde sin competir con los slots
editoriales:

- `scripts/windows/backfill_stats.ps1` — corre `stat_coverage report` y
  `match_events enrich-pending` para todas las competiciones integradas.
  Se registra como `futbol_stats_backfill_weekly` los martes a las
  `05:00`.
- `scripts/windows/backfill_scorers.ps1` — variante reducida solo para
  goleadores, util como rescate puntual fuera del slot semanal.

Ambos aceptan `-Season`, `-LimitPerCompetition`, `-IncludeErrors` y
`-DryRun`.

## Troubleshooting

| Sintoma | Diagnostico rapido |
|---------|--------------------|
| `top_scorer_update` queda en draft con error de cobertura | `stat_coverage report` para ver ratios; `match_events coverage-report` para detalle de goleadores |
| `standings_coverage_stale>7d` | Forzar refresh manual: `python -m app.pipelines.run_source --source futbolme --competition <slug> --target standings` |
| `results_roundup` se autoaprueba pero falta un resultado | Revisar `scorer_status` y `match_data_coverage` para el partido faltante; reingest del source si es necesario |
| Migracion bloqueada | `alembic current` y verificar que `20260524_0019` corrio tras `20260523_0018` |
