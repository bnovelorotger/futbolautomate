# futbolautomate

Automatizacion en Python para una cuenta de X/Twitter centrada en futbol balear. El proyecto combina scraping de competiciones y noticias, persistencia en base de datos, generacion de piezas editoriales y flujos de publicacion/exportacion.

La documentacion detallada de esta iteracion se conserva en [docs/README_detailed.md](docs/README_detailed.md).

## Version actual

Snapshot del **17 de marzo de 2026**.

Esta version deja cerrada una produccion v1 con estos bloques nuevos o consolidados:

- historico de clasificaciones con `standings_snapshots`
- deteccion de `standings_event` sobre cambios de tabla
- ranking y eventos de `team_form`
- scoring de `match_importance` para partidos destacados
- agregados editoriales `results_roundup` y `standings_roundup`
- `editorial_formatter` como capa determinista previa a exportacion
- `story_importance` para ordenar prioridad dentro del autoexport seguro
- scope automatico v1 acotado a piezas seguras y reversibles

## Que incluye ahora

- Ingesta de partidos, clasificaciones y noticias desde varias fuentes.
- Catalogo de competiciones y reglas editoriales configurables.
- Persistencia con SQLAlchemy y migraciones con Alembic.
- Pipelines CLI con Typer para scraping, consultas y operativa editorial.
- Flujos para aprobacion editorial, exportacion a Typefully y publicacion en X.
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
python -m app.pipelines.typefully_export verify-config
python -m app.pipelines.x_auth start-auth
```

5. Ejecutar tests:

```bash
pytest
```

## Estado actual del desarrollo

- La base tecnica de scraping, persistencia y consultas ya existe y tiene tests.
- El repo contiene capa editorial, cola de aprobacion y release hacia Typefully/X a nivel de codigo.
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
- genera drafts manuales revisables
- `featured_match_preview` sigue manual
- `featured_match_event` sigue manual en produccion v1

Integracion editorial actual:
- viernes -> `preview` general por competicion
- viernes -> `featured_match_preview` como bloque aparte
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
- una pieza por competicion y bloque natural de resultados
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
- apto para Typefully/X

Control de longitud:
- limite por defecto de `280` caracteres
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
- `results_roundup` entra en el carril automatico seguro: `draft -> autoapproval -> dispatch -> Typefully autoexport`
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
- una pieza compacta por competicion usando `standings` actuales
- una salida editorial mas densa que la pieza `standings` simple

Como se construye:
- toma la clasificacion actual ordenada por posicion
- intenta etiquetar zonas relevantes usando `app/config/standings_zones.json`
- prioriza la zona alta y, si existe configuracion, la zona de descenso
- si hay huecos entre bloques, inserta `...`
- si no caben todas las posiciones, recorta y anade `+N equipos mas`

Texto:
- limpio
- breve
- centrado en posiciones y puntos
- sin analisis inventado
- apto para Typefully/X

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
- `standings_roundup` entra en el carril automatico seguro: `draft -> autoapproval -> dispatch -> Typefully autoexport`
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
2. `formatted_text`
3. `text_draft`

Que formatea:
- `results_roundup`
- `standings_roundup`
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
- usa solo estos emojis: `📋`, `📊`, `🔥`, `⚽`
- objetivo de longitud `<= 240`
- si un texto se pasa, reduce secciones opcionales; no corta cadenas arbitrariamente

Menciones y hashtags:
- menciones opcionales via tabla `team_mentions`
- hashtags permitidos:
  - `#TerceraRFEF`
  - `#SegundaRFEF`
  - `#FutbolBalear`
- maximo un hashtag y siempre al final

CLI util para poblar menciones:

```bash
python -m app.pipelines.team_mentions list
python -m app.pipelines.team_mentions upsert --competition tercera_rfef_g11 --team "CD Manacor" --handle cdmanacor
```

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
python -m app.pipelines.typefully_export dry-run --id 68
python -m app.pipelines.editorial_rewrite dry-run --id 68
```

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
- ordena las piezas ya elegibles dentro de `typefully_autoexport`
- no amplia la policy automatica
- no mete narrativas en el carril automatico por si solo

Integracion actual con autoexport:
- primero se aplica la policy normal de `typefully_autoexport`
- despues se ejecutan `quality_checks`
- solo sobre las piezas ya elegibles se calcula `importance_score`
- el orden final es `importance_score desc`, luego `priority desc`, luego `created_at asc` y por ultimo `id asc`
- `dry-run`, `run` y `pending-capacity` muestran `score`, `bucket` y `order`

Limitaciones:
- no persiste `importance_score` en BD; el calculo es al vuelo
- la penalizacion de repeticion es estructural, no semantica
- en produccion v1 no abre todavia el carril automatico para narrativas

## Produccion v1

Esta iteracion cierra una produccion v1 y congela el scope editorial automatico.

Automatico v1:
- `results_roundup`
- `standings_roundup`
- `preview`
- `ranking`

Manual v1:
- `match_result`
- `standings`
- `featured_match_preview`
- `featured_match_event`
- `standings_event`
- `form_event`
- `form_ranking`
- `stat_narrative`
- `metric_narrative`
- `viral_story`

Flujo automatico v1:
- `editorial_ops run-daily`
- `editorial_approval`
- `publication_dispatch`
- `typefully_autoexport`

Flujo final de texto:
1. `rewritten_text`
2. `formatted_text`
3. `text_draft`

Comandos de validacion manual recomendados:

```bash
python -m app.pipelines.editorial_approval dry-run --date 2026-03-17
python -m app.pipelines.editorial_release dry-run --date 2026-03-17
python -m app.pipelines.editorial_release dry-run --date 2026-03-14
python -m app.pipelines.typefully_autoexport status
python -m app.pipelines.typefully_autoexport dry-run --date 2026-03-17
```

Notas operativas:
- `results_roundup` y `standings_roundup` son la salida principal de resultados y clasificacion
- `match_result` y `standings` se mantienen como fallback/legacy manual
- `preview` y `ranking` siguen siendo piezas automaticas seguras
- no se anaden nuevas features en esta fase; las mejoras futuras quedan para una iteracion posterior

## Control de versiones

La rama principal del repositorio es `main`. A partir de este punto, cada cambio debe entrar mediante commits pequenos y ramas de trabajo acotadas.
