# futbolautomate

Automatizacion en Python para una cuenta de X/Twitter centrada en futbol balear. El proyecto combina scraping de competiciones y noticias, persistencia en base de datos, generacion de piezas editoriales y flujos de publicacion/exportacion.

La documentacion detallada de esta iteracion se conserva en [docs/README_detailed.md](docs/README_detailed.md).

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
- no se autoaprueban ni se autoexportan en esta fase
- quedan listos para revision humana en la cola editorial

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
- no entran en autoapproval
- no entran en autoexport

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
- genera drafts manuales revisables
- no entra en planner
- no entra en autoapproval
- no entra en autoexport

Limitaciones:
- usa standings actuales, no una prediccion del contexto de jornada
- depende de que existan partidos `scheduled` con fecha futura en BD
- la importancia es editorial y determinista; no modela historial de enfrentamientos ni contexto externo

## Control de versiones

La rama principal del repositorio es `main`. A partir de este punto, cada cambio debe entrar mediante commits pequenos y ramas de trabajo acotadas.
