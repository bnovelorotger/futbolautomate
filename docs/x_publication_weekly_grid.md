# Parrilla semanal de publicacion en X

Este documento fija la parrilla operativa vigente para futbolbalear. La idea no es publicar todo lo que genera el planner, sino seleccionar una salida pequena y consistente por ventana.

## Criterios

- Priorizar horas con audiencia local despierta y predispuesta: manana y prime time de noche entre semana.
- Evitar bursts: maximo 2 posts por slot de lunes a viernes y 2 posts por slot el fin de semana.
- Separar posts 30 minutos (`X_BROWSER_STAGGER_SECONDS=1800`) para reducir fatiga de autor y dar margen a traccion temprana.
- Mantener piezas de dato puro en ventanas de consulta natural y piezas conversacionales en prime time.
- No confundir carga del planner con salida: la salida real pasa por `publication_schedule.json`, autoapproval/manual review, quality checks y `-PublishLimit`.

## Lectura accionable del algoritmo de X

La revision del repo publico `twitter/the-algorithm` deja tres reglas practicas aplicables aqui:

- Home Mixer compone For You con candidate generation, feature hydration, scoring/ranking y filtros/heuristicas como author diversity, deduplicacion y visibility filtering.
- El heavy ranker predice probabilidades de acciones como favorite, retweet, reply, profile click, good click, negative feedback y report, y las combina con pesos.
- Reply, good click/profile click y ausencia de feedback negativo pesan mas operativamente que publicar mucho; por eso interesa espaciar y elegir ventanas donde haya respuesta temprana.

Fuentes:

- https://github.com/twitter/the-algorithm
- https://raw.githubusercontent.com/twitter/the-algorithm/main/home-mixer/README.md
- https://raw.githubusercontent.com/twitter/the-algorithm-ml/main/projects/home/recap/README.md

## Parrilla semanal

| Dia | Datos | Generacion | Publicacion X | Limite | Tipos publicables | Objetivo |
| --- | --- | --- | --- | --- | --- | --- |
| Lunes | 06:30 + 14:00 | 07:30 | 09:30, 10:00 / 19:30, 20:00 | 2 por slot | `results_roundup`, `standings_roundup`, `top_scorer_update`, `race_narrative`, `milestone_story` | Recap principal del fin de semana repartido manana/noche |
| Martes | 07:00 + 14:00 | 08:30 | 09:30, 10:00 / 19:30, 20:00 | 2 por slot | `ranking`, `standings_roundup` | Mantener presencia con enfoque de clasificacion |
| Miercoles | 07:00 + 14:00 | 08:30 | 09:30, 10:00 / 19:30, 20:00 | 2 por slot | `viral_story`, `metric_narrative`, `stat_narrative` | Piezas conversacionales y de retencion |
| Jueves | 07:00 + 14:00 | 08:30 | 09:30, 10:00 / 19:30, 20:00 | 2 por slot | `top_scorer_update`, `ranking` | Pichichi y contexto de tabla |
| Viernes | 07:00 + 14:00 | 08:00 | 09:30, 10:00 / 19:30, 20:00 | 2 por slot | `featured_match_preview`, `match_impact_scenario` | Previas antes del fin de semana |
| Sabado | 07:00 + 14:00 | 09:30 | 11:00, 11:30 | 2 | `preview` | Previa ligera del dia |
| Domingo | 06:30 + 14:00 + 20:00 | 20:45 | 21:15, 21:45 | 2 | `results_roundup`, `standings_roundup` | Cierre ligero de resultados recientes |

## Detalles por tipo

- `race_narrative` queda planificado los lunes, pero solo se autoaprueba si cumple la compuerta condicional estricta.
- `milestone_story` queda planificado los lunes para no perder oportunidades, pero sigue siendo manual salvo cambio explicito de policy.
- Martes y jueves usan piezas de menor riesgo editorial para sostener presencia sin meter demasiado tono ni demasiada carga.
- Sabado se reserva a `preview` ligera; el `featured_match_preview` sigue concentrado en viernes.
- El digest de Telegram sale a las 22:00, por eso el domingo queda limitado a 2 posts.

## Configuracion que sostiene la parrilla

- `app/config/editorial_schedule.json`: define la carga editorial que puede generar el planner.
- `app/config/publication_schedule.json`: define que tipos son publicables por dia, desde que hora y con que cupo por slot.
- `scripts/windows/setup_scheduler.ps1`: registra las tareas y pasa `-PublishLimit` por slot.
- `app/core/config.py`: `x_browser_stagger_seconds=1800` y `x_browser_release_action_limit=4`; las tareas L-V bajan el cupo a 2.

## Interpretacion del plan diario de Telegram

- `carga total del planner`: tareas/editoriales que el sistema puede intentar generar.
- `publicables hoy`: piezas que pasan policy y quality checks.
- `salida prevista en este slot`: piezas que entran en el limite real de publicacion del slot.
- `publicadas de la jornada`: piezas ya publicadas para la fecha de referencia.

Si el planner muestra 37 tareas el lunes y cada slot publica 2, eso es correcto: 37 es capacidad editorial, 2 es salida real por ventana en X.
