# futbolautomate

Automatizacion en Python para una cuenta de X/Twitter centrada en futbol balear. El proyecto combina scraping de competiciones y noticias, persistencia en base de datos, generacion de piezas editoriales y flujos de publicacion/exportacion.

La documentacion detallada de esta iteracion se conserva en [docs/README_detailed.md](docs/README_detailed.md).

## Version actual

Release **v1.5**. Snapshot del **7 de abril de 2026**.

Esta version deja cerrada una produccion v1 con estos bloques nuevos o consolidados:

- historico de clasificaciones con `standings_snapshots`
- deteccion de `standings_event` sobre cambios de tabla
- ranking y eventos de `team_form`
- scoring de `match_importance` para partidos destacados
- agregados editoriales `results_roundup` y `standings_roundup`
- `editorial_formatter` como capa determinista previa a exportacion
- `editorial_release` + `export_base_service` para generar `exports/export_base.json` como salida estructurada por defecto
- `legacy_export_json_enabled` para reactivar `export/legacy_export.json` via `export_json_service` solo por compatibilidad
- catalogo integrado ampliado con `primera_rfef_baleares`, `tercera_federacion_femenina_g11`, `division_honor_ibiza_form` y `division_honor_menorca`
- planner semanal afinado: lunes cubre `results_roundup + standings_roundup` en las siete integradas, miercoles anade la triada narrativa (`stat_narrative`, `metric_narrative`, `viral_story`) para `tercera_rfef_g11`, `segunda_rfef_g3_baleares` y `tercera_federacion_femenina_g11`, jueves abre un bloque de `preview` para las cinco competiciones principales con una ventana equivalente al viernes, mantiene `ranking` en `primera_rfef_baleares`, y viernes conserva `preview` mas el bloque destacado donde aplica
- `division_honor_mallorca` entra tambien en viernes para `preview` y `featured_match_preview`
- `editorial_summary` usa una ventana editorial corta para previas: se queda con la ronda inmediata y descarta jornadas demasiado lejanas
- `competition_queries.editorial_upcoming_matches` extiende el alcance de previa hasta el siguiente domingo cuando el planner corre jueves o viernes
- `results_roundup` y `standings_roundup` pasan a priorizar una pieza unica completa; el formatter quita hashtags y compacta el titulo antes de recortar marcadores o filas
- `editorial_content_generator` deja de usar `preview:upcoming` y genera `content_key` anclado a jornada, fecha y equipos para evitar previews duplicadas o ambiguas
- `export_base_service` usa `editorial_text_selector` en `preview` y `featured_match_preview` para conservar `viral_formatted_text` cuando aporta mejor salida
- `editorial_release` respeta `scheduled_at`: autoaprueba piezas seguras, pero solo despacha las ya listas
- `editorial_release` recupera tambien candidatas `approved` de ejecuciones anteriores si ya han entrado en ventana y estan listas para publicarse
- `export_base_service` exporta unicamente candidatas en estado `published`
- `standings_roundup` toma como etiqueta de jornada la ultima ronda finalizada aunque la tabla vaya retrasada en `played`, para no reciclar snapshots de ronda vieja
- `export_base_service` deduplica variantes de `standings_roundup` por ronda real y fija el path PNG con la fecha del snapshot, no con fechas heredadas del payload
- `editorial_approval_policy` pasa a ser sensible al dia: martes/miercoles puede autoaprobar `stat_narrative`, `metric_narrative` y `viral_story` solo si pasan `quality_checks`
- `editorial_approval_policy` deja de depender de que el draft se haya creado el mismo dia y toma por ventana real las piezas antiguas que siguen siendo elegibles
- `publication_dispatch` trata `preview` como pieza lista antes del kickoff y el repositorio puede actualizar drafts legacy de previa aunque cambie el `source_summary_hash`
- `editorial_quality_checks` acepta tambien titulos compactos de roundup cuando el formatter recorta cabecera para ajustar longitud
- export visual PNG de `standings_roundup` durante `export_base`, con `image_path` por item y tolerancia a fallos de render
- `standings_image_mapper` intenta reconstruir la clasificacion completa desde BD, no solo desde el payload resumido, y resalta lider, zonas y equipos seguidos cuando aplica
- la tarjeta visual ajusta altura, densidad de tabla y columnas de forma automatica segun filas y estadisticas disponibles
- `editorial_formatter` refina branding y titulos narrativos: `DH Mallorca`, `💪🏼 Forma`, `📈 Tendencia` y `🔥 Dato`
- `viral_formatted_text` como capa compacta para export seguro en resultados, clasificaciones, previas y rankings
- `team_socials` + `social_enricher` para insertar menciones de clubes sin duplicados
- `team_name_aliases.json` + `team_name_normalizer` para fijar naming editorial consistente
- dataset curado `scripts/team_socials_dataset.json` para poblar `team_socials`
- `story_importance` para ordenar prioridad dentro del release seguro
- scope automatico v1 controlado por dia, calidad y reversibilidad de la pieza

## Que incluye ahora

- Ingesta de partidos, clasificaciones y noticias desde varias fuentes.
- Catalogo de competiciones y reglas editoriales configurables.
- Persistencia con SQLAlchemy y migraciones con Alembic.
- Pipelines CLI con Typer para scraping, consultas y operativa editorial.
- Flujos para aprobacion editorial, exportacion JSON local, snapshots estructurados y publicacion en X.
- Suite de tests unitarios e integracion.

## Estructura principal

```text
app/             Codigo fuente principal
docs/            Documentacion y notas operativas
migrations/      Migraciones de base de datos
scripts/         Scripts auxiliares para cron y Windows
tests/           Tests unitarios e integracion
.env.example     Variables de entorno de referencia
pyproject.toml   Dependencias y configuracion del proyecto
```

## Como ejecutar

1. Crear entorno virtual e instalar dependencias:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Crear `.env` a partir de `.env.example` y ajustar al menos `DATABASE_URL`.

3. Aplicar migraciones:

```bash
alembic upgrade head
```

4. Ejecutar pipelines principales:

```bash
python -m app.pipelines.run_daily
python -m app.pipelines.run_source --source futbolme --competition division_honor_mallorca --target matches
python -m app.pipelines.editorial_ops preview-day --date 2026-03-16
python -m app.pipelines.standings_history latest --competition tercera_rfef_g11
python -m app.pipelines.standings_events show --competition tercera_rfef_g11
python -m app.pipelines.team_form ranking --competition tercera_rfef_g11
python -m app.pipelines.results_roundup show --competition tercera_rfef_g11
python -m app.pipelines.editorial_quality_checks dry-run --date 2026-03-22
python -m app.pipelines.editorial_release dry-run --date 2026-03-26
python -m app.pipelines.export_base generate --date 2026-03-26
python -m app.pipelines.x_auth start-auth
```

5. Ejecutar tests:

```bash
pytest
```

## Estado actual del desarrollo

- La base tecnica de scraping, persistencia y consultas ya existe y tiene tests.
- El catalogo operativo ya no se limita a tres competiciones: ahora incluye tambien `primera_rfef_baleares`, `tercera_federacion_femenina_g11`, `division_honor_ibiza_form` y `division_honor_menorca`.
- El repo contiene capa editorial, cola de aprobacion y release hacia `exports/export_base.json`, con `export/legacy_export.json` solo como compatibilidad opcional y publicacion en X todavia desacoplada.
- El release seguro ya diferencia entre aprobacion y publicacion: una previa futura puede quedar `approved` sin entrar todavia en `published` ni en el snapshot exportado.
- `export_base` ya puede adjuntar un artefacto visual PNG para `standings_roundup`; el entorno que genere el snapshot necesita `playwright install chromium`.
- La operativa real depende de credenciales, base de datos y tareas programadas locales.
- Falta endurecer el flujo de trabajo de equipo: ramas, CI, politicas de revision y despliegue.

## Historico de clasificacion

- El sistema mantiene la tabla `standings` como snapshot actual de trabajo.
- El historico se guarda aparte en `standings_snapshots`, una fila por equipo y timestamp de ingesta.
- Cada snapshot historico conserva: competicion, equipo, posicion, puntos, partidos jugados, victorias, empates, derrotas, goles a favor, goles en contra, diferencia, `snapshot_date`, `snapshot_timestamp` y fuente.
- La ingesta actual de standings sigue funcionando igual para consultas operativas; el historico se persiste en paralelo y no rompe el flujo existente.

## Eventos de tabla detectados

Eventos soportados hoy:
- `new_leader`
- `entered_playoff`
- `left_playoff`
- `entered_relegation`
- `left_relegation`
- `biggest_position_rise`
- `biggest_position_drop`

Reglas:
- el sistema compara el ultimo snapshot disponible contra el snapshot anterior de la misma competicion
- no mezcla competiciones
- las zonas relevantes se configuran por competicion en `app/config/standings_zones.json`
- si una competicion no tiene zonas configuradas, no inventa playoff ni descenso

Configuracion actual de zonas:
- `tercera_rfef_g11`: playoff `[2,3,4,5]`, descenso `[14,15,16,17,18]`
- `segunda_rfef_g3_baleares`: playoff `[2,3,4,5]`, descenso `[14,15,16,17,18]`
- `division_honor_mallorca`: sin zonas editoriales activas por ahora

## CLI de snapshots y eventos

Inspeccion:

```bash
python -m app.pipelines.standings_history latest --competition tercera_rfef_g11
python -m app.pipelines.standings_history compare --competition tercera_rfef_g11
python -m app.pipelines.standings_events show --competition tercera_rfef_g11
```

Generacion manual de borradores:

```bash
python -m app.pipelines.standings_events generate --competition tercera_rfef_g11
python -m app.pipelines.standings_events generate --competition segunda_rfef_g3_baleares
```

Resultado editorial:
- los eventos de tabla se guardan como `content_type=standings_event`
- entran en `draft`
- quedan listos para revision humana en la cola editorial
- en produccion v1 siguen fuera del carril automatico

Limitaciones actuales:
- la comparacion usa solo el ultimo snapshot y el anterior, no una serie temporal larga
- no hay aun detector robusto de equipo revelacion ni lectura larga de tendencias encadenadas
- `division_honor_mallorca` ya guarda historico, pero no tiene zonas de playoff/descenso activadas todavia

## Team Form

La capa `team_form` calcula forma reciente de equipos a partir de partidos `finished` ya guardados en BD.

Para cada equipo calcula:
- ultimos `N` partidos, por defecto `5`
- secuencia reciente tipo `WWWDW`
- puntos obtenidos en esa ventana
- goles a favor y en contra
- diferencia de goles

Orden del ranking:
1. puntos en los ultimos `N`
2. diferencia de goles
3. goles a favor

CLI:

```bash
python -m app.pipelines.team_form show --competition tercera_rfef_g11
python -m app.pipelines.team_form ranking --competition tercera_rfef_g11
python -m app.pipelines.team_form generate --competition tercera_rfef_g11
```

Salida editorial soportada:
- `content_type=form_ranking`
- `content_type=form_event`

Eventos derivados:
- `best_form_team`
- `worst_form_team`
- `longest_win_streak_recent`
- `longest_loss_streak_recent`

Estado operativo:
- se generan en `draft`
- no entran en planner
- `form_ranking` sigue manual
- `form_event` sigue manual en produccion v1

Limitaciones:
- la ventana usa solo partidos `finished`
- la secuencia se calcula en orden reciente, del mas nuevo al mas antiguo
- en competiciones con `tracked_teams`, como `segunda_rfef_g3_baleares`, el ranking se limita a los equipos editoriales relevantes

## Match Importance

La capa `match_importance` detecta partidos destacados proximos usando scoring determinista sobre clasificacion actual, forma reciente y cercania competitiva.

Factores de scoring:
- posicion de ambos equipos en la tabla actual
- distancia entre ambos en la clasificacion
- si ambos estan en zona alta
- si ambos estan en zona de playoff o cerca
- si ambos estan en zona baja o cerca
- si ambos llegan en buena dinamica reciente
- si ambos llegan en mala dinamica reciente
- si el cruce es entre rivales directos

Tags editoriales soportados:
- `title_race`
- `top_table_match`
- `playoff_clash`
- `relegation_clash`
- `hot_form_match`
- `cold_form_match`
- `direct_rivalry`

Configuracion:
- vive en `app/config/match_importance.json`
- permite ajustar por competicion:
  - `top_zone_positions`
  - `playoff_positions`
  - `bottom_zone_positions`
  - `direct_rival_gap_max`
  - `near_playoff_margin`
  - `near_bottom_margin`
  - pesos de scoring por tag

CLI:

```bash
python -m app.pipelines.match_importance show --competition tercera_rfef_g11
python -m app.pipelines.match_importance top --competition tercera_rfef_g11 --limit 5
python -m app.pipelines.match_importance generate --competition tercera_rfef_g11 --limit 3
```

Salida editorial soportada:
- `content_type=featured_match_preview`
- `content_type=featured_match_event`

Ejemplos de borradores:

```text
Partido destacado del fin de semana en 3a RFEF Baleares: CD Manacor vs RCD Mallorca B, duelo directo por el liderato.
```

```text
Choque de equipos en forma en 3a RFEF Baleares: CD Manacor y RCD Mallorca B llegan con 11 y 13 puntos en los ultimos 5 partidos.
```

Estado operativo:
- los viernes entra en el planner como bloque separado de `featured_match_preview`
- ya cubre `tercera_rfef_g11`, `segunda_rfef_g3_baleares`, `primera_rfef_baleares`, `tercera_federacion_femenina_g11`, `division_honor_mallorca`, `division_honor_ibiza_form` y `division_honor_menorca`
- genera drafts manuales revisables
- `featured_match_preview` sigue manual
- `featured_match_event` sigue manual en produccion v1

Integracion editorial actual:
- jueves -> `preview` general por competicion con horizonte extendido para capturar la jornada inmediata del viernes
- viernes -> `preview` general por competicion
- viernes -> `featured_match_preview` como bloque aparte
- `division_honor_mallorca` queda ya incluida en ambos bloques del viernes
- el bloque destacado usa `match_importance` y genera dos drafts:
  - `featured_match_preview`
  - `featured_match_event`
- ambos quedan en `draft` para revision humana en `editorial_queue`

Limitaciones:
- usa standings actuales, no una prediccion del contexto de jornada
- depende de que existan partidos `scheduled` con fecha futura en BD
- la importancia es editorial y determinista; no modela historial de enfrentamientos ni contexto externo

## Results Roundup

La capa `results_roundup` agrega resultados finales de una misma competicion en una unica pieza editorial compacta.

Que genera:
- `content_type=results_roundup`
- una sola pieza por competicion y bloque natural de resultados
- prioridad editorial alta para los slots de resultados del planner

Como agrupa:
- primero toma partidos `finished` de la competicion hasta la fecha de referencia
- intenta agrupar por `round_name`
- si no hay jornada clara, cae al bloque natural por fecha
- ordena de forma estable por fecha, hora y equipos

Texto:
- limpio
- breve
- centrado en competicion y marcadores
- sin analisis inventado
- apto para `exports/export_base.json` y para publicacion posterior en X

Control de longitud:
- limite por defecto de `280` caracteres
- antes de cortar marcadores intenta quitar hashtags y compactar el titulo
- incluye tantos marcadores como quepan
- si no caben todos, recorta y anade una linea final tipo `+N resultados mas`

CLI:

```bash
python -m app.pipelines.results_roundup show --competition tercera_rfef_g11
python -m app.pipelines.results_roundup show --competition segunda_rfef_g3_baleares --date 2026-03-16
python -m app.pipelines.results_roundup generate --competition tercera_rfef_g11
python -m app.pipelines.results_roundup generate --competition tercera_rfef_g11 --json
```

Ejemplo:

```text
RESULTADOS | 3a RFEF Baleares | Jornada 26

CE Alpha 2-0 CE Delta
CE Beta 1-0 CE Epsilon
CE Gamma 2-1 CE Foxtrot
```

Integracion editorial:
- lunes y domingo el planner usa `results_roundup` como bloque principal de resultados
- `match_result` individual sigue existiendo en el backend y no se elimina en esta fase
- `results_roundup` sigue generandose primero en `draft`
- `results_roundup` entra en el carril seguro: `draft -> quality_checks -> autoapproval -> dispatch -> export_base`
- en `phase=1` se trata como pieza segura junto a `standings_roundup`, `preview` y `ranking`
- `match_result` individual sigue existiendo para casos legacy o gestion manual, pero ya no es la salida principal de resultados del planner

Diferencia frente a `match_result`:
- `match_result` genera una pieza por partido
- `results_roundup` agrupa la jornada o bloque natural en una sola pieza
- la estrategia recomendada ahora es usar `results_roundup` como salida principal y mantener `match_result` como capa legacy/manual reversible

## Standings Roundup

La capa `standings_roundup` aplica el mismo patron de agregacion a la clasificacion actual de una competicion.

Que genera:
- `content_type=standings_roundup`
- una sola pieza compacta por competicion usando `standings` actuales
- una salida editorial mas densa que la pieza `standings` simple

Como se construye:
- toma la clasificacion actual ordenada por posicion
- intenta etiquetar zonas relevantes usando `app/config/standings_zones.json`
- usa como jornada visible la ultima ronda realmente finalizada si va por delante del `played` agregado en standings
- prioriza la zona alta y, si existe configuracion, la zona de descenso
- si hay huecos entre bloques, inserta `...`
- si no caben todas las posiciones, recorta y anade `+N equipos mas`

Texto:
- limpio
- breve
- centrado en posiciones y puntos
- sin analisis inventado
- apto para `exports/export_base.json` y para publicacion posterior en X
- si aprieta la longitud, intenta quitar hashtags y compactar el titulo antes de recortar filas

CLI:

```bash
python -m app.pipelines.standings_roundup show --competition tercera_rfef_g11
python -m app.pipelines.standings_roundup generate --competition tercera_rfef_g11
```

Ejemplo:

```text
CLASIFICACION | 3a RFEF Baleares

1. RCD Mallorca B - 66 pts
2. CD Manacor - 64 pts [PO]
3. SCR Pena Deportiva - 57 pts [PO]
...
14. CD Son Cladera - 25 pts [DESC]
15. SD Portmany - 24 pts [DESC]
```

Integracion editorial:
- lunes el planner usa `results_roundup + standings_roundup`
- domingo el planner usa `results_roundup + standings_roundup` para las competiciones activas del cierre de jornada
- `standings_roundup` se genera en `draft`
- `standings_roundup` entra en el carril seguro: `draft -> quality_checks -> autoapproval -> dispatch -> export_base`
- en `phase=1` se trata como pieza segura junto a `results_roundup`, `preview` y `ranking`
- `standings` individual sigue existiendo como capa legacy o fallback manual

Diferencia frente a `standings`:
- `standings` simple resume solo la parte alta en una pieza corta
- `standings_roundup` agrega una lectura mas completa y editorial de la tabla
- la estrategia recomendada ahora es usar `standings_roundup` como salida principal de clasificacion y mantener `standings` como capa legacy/manual reversible

## Editorial Formatter

La capa `editorial_formatter` prepara una version final determinista del texto antes de exportar.

Flujo actualizado:
- `content_generator`
- `editorial_formatter`
- `editorial_rewriter` opcional
- exportacion

Prioridad final de texto en export:
1. `rewritten_text`
2. `viral_formatted_text`
3. `enriched_text`
4. `formatted_text`
5. `text_draft`

Que formatea:
- `results_roundup`
- `standings_roundup`
- `standings`
- `preview`
- `ranking`
- `stat_narrative`
- `metric_narrative`
- `viral_story`
- `form_event`
- `standings_event`
- `featured_match_event`
- `match_result` preparado para casos especiales

Reglas:
- todo es determinista
- no inventa datos
- normaliza aliases editoriales desde `app/config/team_name_aliases.json` antes de resumir o enriquecer
- usa branding corto por competicion, incluido `DH Mallorca` para `division_honor_mallorca`
- usa titulos narrativos por etiqueta: `💪🏼 Forma`, `📈 Tendencia` y `🔥 Dato`
- objetivo de longitud `<= 240`
- si un texto se pasa, reduce secciones opcionales; no corta cadenas arbitrariamente

Menciones y hashtags:
- `team_socials` es la fuente principal de handles
- `team_mentions` queda como fallback legacy cuando aun no existe identidad social curada
- `social_enricher` solo inserta menciones si caben en longitud, no duplica handles y respeta `MAX_MENTIONS_PER_POST`
- `editorial_quality_checks` falla si el texto final supera 240 caracteres, repite handles o usa hashtags de mas
- hashtags permitidos:
  - `#TerceraRFEF`
  - `#SegundaRFEF`
  - `#FutbolBalear`
- maximo dos hashtags, sin duplicados y siempre al final

Configuracion relevante:

- `ENABLE_TEAM_MENTIONS=true`
- `MAX_MENTIONS_PER_POST=3`

Bootstrap inicial de identidades sociales:

```bash
alembic upgrade head
python scripts/seed_team_socials.py
python -m app.pipelines.team_mentions upsert --competition tercera_rfef_g11 --team "CD Manacor" --handle cdmanacor
```

Notas:
- `scripts/seed_team_socials.py` arranca con bootstrap legacy desde `team_mentions`
- despues aplica el dataset curado `scripts/team_socials_dataset.json`, que puede sobrescribir el bootstrap si hay mejor dato
- `social_identity_service` resuelve por competicion, actividad, seguidores aproximados e identidad normalizada del club
- `team_name_normalizer` convierte nombres tecnicos como `Atletico Baleares` o `SCR Pena Deportiva` a naming editorial consistente

Ejemplo antes vs despues:

```text
Antes
RESULTADOS | 3a RFEF Baleares | Jornada 26

CD Manacor 2-1 CE Mercadal
RCD Mallorca B 3-0 CE Santanyi
```

```text
Despues
📋 RESULTADOS

3a RFEF Baleares
Jornada 26

CD Manacor @cdmanacor 2-1 CE Mercadal
RCD Mallorca B 3-0 CE Santanyi

⚽ 6 goles en la jornada

#TerceraRFEF
```

Como probarlo:

```bash
python -m app.pipelines.results_roundup generate --competition tercera_rfef_g11
python -m app.pipelines.standings_roundup generate --competition tercera_rfef_g11
python -m app.pipelines.editorial_quality_checks dry-run --date 2026-03-22
python -m app.pipelines.editorial_release dry-run --date 2026-03-22
python -m app.pipelines.editorial_rewrite dry-run --id 68
```

## Team Socials y Social Enricher

La iteracion actual introduce una tabla nueva `team_socials` como fuente primaria de identidad social de clubes.

Cada fila puede guardar:
- `team_name`
- `competition_slug`
- `x_handle`
- `followers_approx`
- `activity_level`
- `is_shared_handle`
- `is_active`

Resolucion de identidad:
- primero intenta coincidencia exacta de `team_name + competition_slug` en `team_socials`
- si no existe, busca otra fila activa del mismo equipo
- despues prueba coincidencia por identidad normalizada del club
- si sigue sin encontrar nada, cae al sistema legacy `team_mentions`

Uso operativo:
- `editorial_formatter` puede producir texto formateado y luego enriquecerlo con handles
- `editorial_formatter` tambien puede producir `viral_formatted_text` mas compacto para salida social
- `editorial_text_selector` prioriza `viral_formatted_text` y luego `enriched_text` cuando no hay `rewritten_text`
- el enriquecimiento esta pensado para `results_roundup`, `standings`, `standings_roundup`, `preview`, `ranking` y piezas con equipos identificables en `source_payload`
- el limite de menciones por post es configurable y se valida otra vez en `quality_checks`

## Export base del release

La salida automatica actual del release no crea drafts en un canal externo. Genera por defecto `exports/export_base.json`.

Flujo actual:
- `editorial_quality_checks`
- `editorial_approval`
- `publication_dispatch`
- `export_base_service`

Que persiste:
- `scope`, `target_date`, `window_start`, `window_end`, `generated_at` y `total_items`
- bloques por `competition_slug` y `content_type`
- por cada item: `id`, `text`, `selected_text_source`, `image_path`, `priority` y `created_at`

Reglas operativas:
- solo exporta piezas ya `published`, con `published_at` y texto resoluble para salida
- usa ventana semanal y reglas distintas para previas, post-jornada y piezas semanales
- `publication_dispatch` publica `preview` antes del kickoff y usa `scheduled_at` como gating para el resto de piezas
- `editorial_release` puede despachar tanto las autoaprobadas del run actual como piezas `approved` de runs anteriores que ya esten listas
- en `preview` y `featured_match_preview` usa `editorial_text_selector`, por lo que puede elegir `rewritten_text`, `viral_formatted_text`, `formatted_text` o `text_draft`
- en el resto usa `rewritten_text`, despues `formatted_text` y por ultimo `text_draft`
- deduplica por `content_key` o por marcador estructural derivado de `source_payload`, y en `standings_roundup` prioriza la ronda/parte mas reciente
- el fichero `exports/export_base.json` es artefacto local de salida, no fuente editable del sistema

Regeneracion manual:
- `python -m app.pipelines.export_base generate --date 2026-03-26`

## Export visual standings

`standings_roundup` puede generar una tarjeta PNG adicional durante `export_base` sin tocar planner, scoring, approval ni release.

Piezas:
- template HTML: `app/templates/standings_card.html`
- mapper de contexto: `app/services/standings_image_mapper.py`
- renderer HTML/PNG: `app/services/image_renderer.py`
- orquestacion: `app/services/standings_card_service.py`

Salida:
- PNG final en `exports/images/{competition_slug}/{date}/standings_roundup_{id}.png`
- HTML temporal en `exports/tmp/images/{competition_slug}/{date}/standings_roundup_{id}.html`
- `export_base.json` incluye `image_path` solo cuando `content_type=standings_roundup`
- si el render falla, el export sigue y `image_path` queda en `null`

Comportamiento actual:
- intenta usar la clasificacion completa de `current_standings` cuando la candidata esta ligada a una sesion de BD; si no puede, cae al `source_payload`
- marca visualmente lider, playoff, descenso y equipos seguidos en competiciones con `tracked_teams`
- ajusta altura final, tamanos tipograficos y grid de columnas segun numero real de filas y estadisticas presentes
- ya no fuerza `10` filas ni una altura fija si el mapper resuelve mejor el layout
- usa la fecha objetivo del snapshot para construir rutas estables de salida, incluso si la candidata arrastra otra `reference_date`

Dependencia operativa:

```bash
playwright install chromium
```

## Legacy export JSON

Si activas `LEGACY_EXPORT_JSON_ENABLED=true`, el release vuelve a generar ademas `export/legacy_export.json`.

Reglas operativas:
- usa `export_json_service`
- queda orientado a compatibilidad con consumidores antiguos
- su ruta por defecto es `export/legacy_export.json`

## Story Importance

La capa `story_importance` puntua `content_candidates` de forma determinista para ordenar prioridad editorial.

Factores que usa:
- `content_type_weight`
- intensidad del evento
- contexto de tabla
- `match_importance_score` si existe
- senales de forma
- penalizacion por repeticion reciente

Configuracion:
- [story_importance.json](c:/Users/bnove/Documents/futbolbalear/app/config/story_importance.json)
- pesos por `content_type`
- multiplicador por competicion
- intensidades por tipo de historia
- buckets `critical / high / medium / low`

CLI:

```bash
python -m app.pipelines.story_importance show --date 2026-03-17
python -m app.pipelines.story_importance top --date 2026-03-17 --limit 10
python -m app.pipelines.story_importance score --id 68
python -m app.pipelines.story_importance rank-pending
```

Uso actual en produccion v1:
- se mantiene como scoring CLI y como base para politicas condicionales
- no abre carril automatico por si solo; necesita policy activa y `quality_checks` en verde
- el carril seguro se decide por `editorial_approval_policy`, que ahora incluye reglas por dia de semana

Limitaciones:
- no persiste `importance_score` en BD; el calculo es al vuelo
- la penalizacion de repeticion es estructural, no semantica
- no sustituye la validacion editorial ni los quality checks sobre narrativas

## Produccion v1

Esta iteracion mantiene una produccion v1 con automatizacion controlada por tipo de pieza y por dia.

Automatico v1 (base):
- `results_roundup`
- `standings_roundup`
- `preview`
- `ranking`

Automatico v1 (condicional martes/miercoles + quality checks):
- `stat_narrative`
- `metric_narrative`
- `viral_story`

Manual v1:
- `match_result`
- `standings`
- `featured_match_preview`
- `featured_match_event`
- `standings_event`
- `form_event`
- `form_ranking`

Flujo automatico v1:
- `editorial_ops run-daily`
- `editorial_release`
  - `editorial_quality_checks`
  - `editorial_approval`
  - `publication_dispatch`
  - `exports/export_base.json`

Flujo final de texto:
1. `rewritten_text`
2. `viral_formatted_text`
3. `enriched_text`
4. `formatted_text`
5. `text_draft`

Comandos de validacion manual recomendados:

```bash
python -m app.pipelines.editorial_approval dry-run --date 2026-03-17
python -m app.pipelines.editorial_quality_checks dry-run --date 2026-03-26
python -m app.pipelines.editorial_release dry-run --date 2026-03-26
python -m app.pipelines.editorial_release run --date 2026-03-26
python -m app.pipelines.export_base generate --date 2026-03-26
python -m app.pipelines.system_check editorial-readiness
```

Notas operativas:
- `results_roundup` y `standings_roundup` son la salida principal de resultados y clasificacion
- `match_result` y `standings` se mantienen como fallback/legacy manual
- `preview` y `ranking` siguen siendo piezas automaticas seguras
- el planner puede adelantar `preview` al jueves y al viernes sin perder la jornada inmediata del siguiente domingo
- `stat_narrative`, `metric_narrative` y `viral_story` pueden salir en automatico solo martes/miercoles y solo con quality checks en verde
- `editorial_release` no se limita a lo generado en el mismo dia: tambien puede publicar candidatas ya aprobadas si su ventana real ya ha llegado
- `editorial_release` genera `exports/export_base.json` como snapshot estructurado por defecto
- `export_base generate` regenera ese mismo snapshot de forma manual si lo necesitas fuera del release
- `LEGACY_EXPORT_JSON_ENABLED=true` reactiva `export/legacy_export.json` solo para compatibilidad
- no se anaden nuevas features en esta fase; las mejoras futuras quedan para una iteracion posterior

## Control de versiones

La rama principal del repositorio es `main`. A partir de este punto, cada cambio debe entrar mediante commits pequenos y ramas de trabajo acotadas.
