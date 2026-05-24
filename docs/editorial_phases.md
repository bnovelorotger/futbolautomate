# Fases editoriales

Documento operativo del servicio `EditorialPhaseService`
(`app/services/editorial_phase.py`) y su pipeline CLI asociado. La fase
editorial describe en que momento del calendario competitivo esta cada
competicion para decidir, *por competicion*, que tipos de contenido tienen
sentido generar y publicar.

## Estados (`EditorialSeasonPhase`)

| Fase | Cuando se entra | Senal en BD |
|------|-----------------|--------------|
| `OFFSEASON` | Sin partidos cargados o el ultimo finished excede la ventana de wrap | Default cuando no hay datos relevantes |
| `PRESEASON` | El primer partido programado esta dentro de `PRESEASON_DAYS_BEFORE_FIRST_MATCH` (14 dias) y no hay finished aun | Match futuro proximo, cero finished |
| `REGULAR_SEASON` | Hay partidos `scheduled`/`live` futuros y al menos un `finished` previo | Liga regular en curso |
| `PLAYOFFS` | Slug detectado como playoff (definicion o nombre contiene `playoff`) con partidos futuros, o una competicion regular con un playoff hijo activo | Bracket vivo |
| `SEASON_WRAP` | Sin partidos futuros pero el ultimo finished esta dentro de `SEASON_WRAP_DAYS_AFTER_LAST_MATCH` (14 dias) | Cierre/post-temporada |

`global_phase()` agrega los estados por prioridad
(`PLAYOFFS > SEASON_WRAP > REGULAR_SEASON > PRESEASON > OFFSEASON`) y devuelve
la fase dominante mas el detalle por competicion. Las competiciones con
`has_data=False` se ignoran salvo que ninguna otra tenga datos.

## Detección de playoffs

Una competicion es playoff si:

1. Su `CompetitionDefinition.competition_type == "playoff"` en
   `app/config/competitions.json`, o
2. Su slug contiene `playoff` (fallback historico).

Los playoffs **hijos** se asocian a su competicion regular por
`parent_competition` o, en su defecto, por prefijo de slug
(`<regular>_<sufijo>`). Cuando una competicion regular tiene un hijo en
`PLAYOFFS` o `SEASON_WRAP`, hereda esa fase con razon
`child_playoff_active:<slug>` / `child_playoff_recently_finished:<slug>`.

## Reglas de contenido permitido

`content_type_allowed(competition_slug, content_type, reference_date)`
devuelve `(allowed, state, reason)`. Las whitelists actuales son:

- `REGULAR_SEASON` → tipos editoriales habituales (match_result,
  results_roundup, standings*, ranking, race_narrative, milestone_story,
  top_scorer_update, viral_story, metric_narrative, stat_narrative,
  featured_match_preview, match_impact_scenario, preview).
- `PLAYOFFS` (competicion playoff) → match_result, results_roundup,
  featured_match_preview, preview, playoff_bracket.
- `PLAYOFFS` (competicion regular con hijo activo) → ningun contenido
  automatico; la pieza relevante la genera el slug hijo.
- `SEASON_WRAP` (regular) → results_roundup, match_result, standings*,
  ranking, milestone_story, top_scorer_update, viral_story,
  metric_narrative, stat_narrative, **season_wrap_stats**,
  **season_wrap_outcomes**, playoff_bracket.
- `SEASON_WRAP` (playoff) → results_roundup, match_result, playoff_bracket,
  season_wrap_outcomes.
- `PRESEASON` → featured_match_preview, preview, viral_story.
- `OFFSEASON` → nada.

Cuando una competicion **no tiene datos** (`has_data=False`) se considera
permisivo (`allowed=True, reason=None`) para no bloquear arranque de
temporadas nuevas.

## Integracion en el pipeline

- `EditorialPlannerService.plan_for_date` filtra cada regla de la parrilla
  (`editorial_schedule.json`) por `planning_content_allowed`. Si la fase no
  encaja se loggea `editorial_planner_phase_skipped` y la tarea no entra al
  plan del dia.
- `EditorialQualityChecksService` agrega `candidate_phase_errors` a los
  errores de calidad: las candidatas en playoff que rompen la whitelist se
  marcan con `phase_content_type_blocked:<phase>:<content_type>`.
- `EditorialReleasePipelineService._select_browser_slot_dispatch_ids` aplica
  el mismo filtro de fase al elegir candidatas para el slot de browser,
  incluso si pasaron los chequeos anteriores (defensa en profundidad).

## CLI

```bash
# Estado global y por competicion (legible)
python -m app.pipelines.runner editorial_phase report

# Mismo informe en JSON, fechado
python -m app.pipelines.runner editorial_phase report --date 2026-05-24 --json
```

Salida resumida:

```
fase_global=playoffs
reason=playoff_future_scheduled
tercera_rfef_g11 | regular_season | regular_future_scheduled | future=12 finished=170 last_finished=2026-05-18
tercera_rfef_g11_playoff | playoffs | playoff_future_scheduled | future=4 finished=0 last_finished=-
...
```

## Como anadir una competicion playoff

1. Definirla en `app/config/competitions.json` con
   `competition_type: "playoff"`, `playoff_type` (`ascenso` / `permanencia`)
   y `parent_competition` apuntando al slug regular.
2. Asegurarse de que `editorial_schedule.json` la lista en los dias
   adecuados para `playoff_bracket`, `featured_match_preview` y
   `results_roundup`.
3. (Opcional) Anadir alias en `team_aliases.json` si la fuente trae nombres
   distintos durante los playoffs.

## Como anadir un tipo de contenido nuevo a una fase

Editar los conjuntos en `app/services/editorial_phase.py`:

- `_REGULAR_AUTOMATIC_CONTENT_TYPES`
- `_PLAYOFF_CONTENT_TYPES`
- `_PRESEASON_CONTENT_TYPES`
- `_SEASON_WRAP_CONTENT_TYPES`
- y la rama playoff dentro de `content_type_allowed` si aplica.

Mantener tambien `_PLANNING_TO_CONTENT` sincronizado con
`EditorialPlanningContent`.
