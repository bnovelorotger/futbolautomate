# Futbol Balear Scraper

Base de codigo modular en Python para scraping, normalizacion y persistencia de datos de futbol balear. El proyecto esta pensado como cimiento de un sistema automatizado de resultados, clasificaciones, proximos partidos y noticias.

## Stack

- Python 3.11+
- PostgreSQL
- SQLAlchemy 2.x
- Pydantic
- Requests + BeautifulSoup
- Playwright cuando una fuente lo requiera
- Pytest
- Alembic

## Estado actual

Integraciones con codigo y tests:

- `soccerway`: base de parser para partidos y clasificaciones.
- `futbolme`: integracion productiva real para `Division Honor Mallorca`, `3a RFEF Grupo 11` y `2a RFEF Grupo 3` en temporada 2025-26.
- `ffib`: parser de noticias publicas.
- `diario_mallorca`: RSS real de Deportes.
- `ultima_hora`: Atom real de Deportes.

Notas relevantes a fecha de **14 de marzo de 2026**:

- Futbolme no expone una ruta vigente usable para `Regional Preferente Mallorca`. Los IDs historicos `36`, `2712`, `3158` y `3163` redirigen a portada.
- La ruta productiva de Futbolme hoy valida y usable para Mallorca es `Division Honor Mallorca`, con ID `4018`.
- La siguiente competicion productiva integrada sobre Futbolme es `3a RFEF Grupo 11`, con ID `3065`.
- La siguiente competicion productiva integrada sobre Futbolme es `2a RFEF Grupo 3`, con ID `3059`, explotada editorialmente solo a traves de los equipos baleares configurados.
- `Preferente Mallorca` queda marcada como `manual_only`: la FFIB la expone, pero `robots.txt` bloquea scraping automatico para `User-agent: *`.
- Varias prioridades del backlog se reflejan ahora con nombre tecnico vigente y nombre editorial separado en el catalogo.
- Soccerway y FFIB siguen encapsulados, pero sus rutas publicas requieren validacion periodica.
- El feed `https://www.diariodemallorca.es/rss/section/15000` devuelve `404`; el feed publico vigente de Deportes es `https://www.diariodemallorca.es/rss/section/2554`.
- El feed `https://www.ultimahora.es/rss/deportes.xml` devuelve `404`; el feed publico vigente de Deportes es `https://www.ultimahora.es/deportes.rss`.

## Catalogo tecnico de competiciones

El catalogo en `app/config/competitions.json` separa:

- `name`: nombre tecnico actual usado por el sistema
- `editorial_name`: etiqueta editorial o historica del backlog
- `status`: estado real de integracion
- `references`: fuentes auditadas para contexto, validacion o uso manual
- `sources`: fuentes automaticas realmente ejecutables por los scrapers

Estado actual del catalogo:

- `integrated`
  - `division_honor_mallorca`
  - `tercera_rfef_g11`
  - `segunda_rfef_g3_baleares`
- `ready_to_integrate`
  - `tercera_federacion_femenina_g11`
  - `division_honor_ibiza_form`
  - `division_honor_menorca`
- `deferred`
  - `juvenil_division_honor_g3`
- `manual_only`
  - `preferente_mallorca`

Renombrados tecnicos relevantes:

- backlog `2a RFEF con equipos baleares` -> codigo tecnico `segunda_rfef_g3_baleares`
- backlog `Primera Nacional femenina con equipos baleares` -> codigo tecnico `tercera_federacion_femenina_g11`
- backlog `Preferente Ibiza` -> codigo tecnico `division_honor_ibiza_form`
- backlog `Preferente Menorca` -> codigo tecnico `division_honor_menorca`

La razon es simple: el sistema no debe confundir el naming editorial con la competicion viva actual de la fuente.

En las competiciones nacionales con foco parcial, el catalogo tambien puede declarar `tracked_teams`. Ese campo marca los equipos que uFutbolBalear debe explotar editorialmente aunque la fuente tecnica cubra el grupo completo.

## Arquitectura

```text
app/
  core/           Configuracion, enums, catalogos, logging, excepciones
  config/         Fuentes, competiciones y alias
  db/             Base SQLAlchemy, modelos, session y repositorios
  schemas/        Contratos Pydantic
  scrapers/       Scrapers por fuente
  normalizers/    Equipos, fechas, estados y texto
  services/       Ingesta, validacion y deduplicacion
  pipelines/      CLI y runners
  utils/          Hashing, robots, tiempo y helpers
tests/
  fixtures/       HTML/XML locales
  unit/           Tests unitarios
  integration/    Tests basicos de ingesta
migrations/
scripts/
```

## Integraciones Futbolme en produccion

### division_honor_mallorca

- Codigo interno: `division_honor_mallorca`
- Fuente: `futbolme`
- ID de competicion: `4018`

### URLs activas validadas

- Partidos y proximos partidos:
  - `https://futbolme.com/resultados-directo/torneo/division-honor-mallorca/4018/calendario`
- Clasificacion:
  - `https://futbolme.com/resultados-directo/torneo/division-honor-mallorca/4018/`

### Selectores usados

Definidos en `app/scrapers/futbolme/selectors.py`:

- Contenido principal: `#contenedorCentral`
- Cabecera de competicion: `#cabeceraTorneo`
- Cabecera de jornada en calendario: `.contenedorTitularTorneoCalendario`
- Bloque de partido: `.cajaPartido`
- Tabla de clasificacion: `#latabla`
- Equipo local: `.equipoPartidoLocal`
- Equipo visitante: `.equipoPartidoVisitante`
- Marcador o hora: `.resultadoPartido`
- Hora visible: `.horaPartido`
- Hora prevista: `.horaPrevistaPartido`

### Decisiones de parseo

- `matches` usa la pestana `calendario`, que hoy devuelve toda la temporada en una sola pagina.
- `standings` usa la pagina raiz de jornada, que expone la clasificacion general en `#latabla`.
- El scraper guarda los partidos futuros en `matches` con `status=scheduled`.
- La fecha de Futbolme llega en castellano; la normalizacion convierte meses y dias al formato parseable interno.
- La URL persistida por partido es la del detalle `Ir al partido`, no la del calendario, para mejorar idempotencia.

### Fragilidades abiertas

- Futbolme mezcla mucho HTML de navegacion global. El parser se limita a `#contenedorCentral` para evitar ruido.
- Algunas jornadas futuras muestran `:` en vez de hora real. En ese caso el partido se guarda como `scheduled` sin `match_time`.
- Futbolme no publica ahora una ruta activa equivalente para `Regional Preferente Mallorca`; si reaparece, conviene integrarla como otra competicion, no reutilizar `division_honor_mallorca`.

### tercera_rfef_g11

- Codigo interno: `tercera_rfef_g11`
- Nombre tecnico: `3a RFEF Grupo 11`
- Nombre editorial: `3a RFEF Baleares`
- Fuente: `futbolme`
- ID de competicion: `3065`

### URLs activas validadas

- Partidos y proximos partidos:
  - `https://futbolme.com/resultados-directo/torneo/tercera-federacion-grupo-11/3065/calendario`
- Clasificacion:
  - `https://futbolme.com/resultados-directo/torneo/tercera-federacion-grupo-11/3065/`

### Cobertura validada

- resultados
- clasificacion
- calendario completo
- proximos partidos

### Decisiones de integracion

- reutiliza el mismo scraper y parser de Futbolme que `division_honor_mallorca`
- se corrigio el parseo de nombres duplicados movil/escritorio, por ejemplo `RCD Mallorca B`
- el upsert de standings ahora tolera mejoras de parsing sin duplicar filas

### Fragilidades abiertas

- Futbolme mantiene algunos partidos pendientes antiguos con `status=scheduled`; las consultas de `upcoming` pueden mostrar arrastres de jornadas anteriores no cerradas.
- El shell de Windows puede mostrar algun acento roto en consola aunque el dato persistido en BD este correcto.

### segunda_rfef_g3_baleares

- Codigo interno: `segunda_rfef_g3_baleares`
- Nombre tecnico: `2a RFEF Grupo 3`
- Nombre editorial: `2a RFEF con equipos baleares`
- Fuente: `futbolme`
- ID de competicion: `3059`

### URLs activas validadas

- Partidos y proximos partidos:
  - `https://futbolme.com/resultados-directo/torneo/segunda-federacion-grupo-3/3059/calendario`
- Clasificacion:
  - `https://futbolme.com/resultados-directo/torneo/segunda-federacion-grupo-3/3059/`

### Cobertura validada

- resultados
- clasificacion del grupo
- calendario completo
- proximos partidos

### Capa editorial balear dentro del grupo

La fuente tecnica almacena el grupo completo, pero la explotacion editorial puede filtrar automaticamente solo los partidos con al menos un equipo balear.

Equipos rastreados hoy en catalogo:

- `UD Poblense`
- `Atletico Baleares`
- `CD Ibiza Islas Pitiusas`
- `CE Andratx`
- `UE Porreres`

Esto permite dos usos simultaneos:

- persistir todo el grupo para mantener clasificacion y contexto
- explotar solo los partidos relevantes para uFutbolBalear con `--relevant-only`

### Decisiones de integracion

- reutiliza el mismo scraper y parser de Futbolme que las competiciones ya integradas
- el parser de standings tolera badges como `1-1` o `10-10` en la celda de posicion
- `query_competition` puede devolver grupo completo o solo la capa balear
- `editorial_summary` filtra por defecto la capa balear en partidos y ventanas, pero mantiene la clasificacion completa del grupo

### Fragilidades abiertas

- la lista de `tracked_teams` es deliberadamente explicita y debe revisarse cuando cambie la composicion balear del grupo en una nueva temporada
- Futbolme puede dejar partidos antiguos como `scheduled`, asi que `upcoming` debe interpretarse con ese ruido en mente

## Noticias RSS en produccion

### Fuentes activas validadas

- Diario de Mallorca Deportes:
  - feed solicitado originalmente: `https://www.diariodemallorca.es/rss/section/15000`
  - feed vigente usado por el scraper: `https://www.diariodemallorca.es/rss/section/2554`
- Ultima Hora Deportes:
  - feed solicitado originalmente: `https://www.ultimahora.es/rss/deportes.xml`
  - feed vigente usado por el scraper: `https://www.ultimahora.es/deportes.rss`

### Campos persistidos

- `title`
- `source_name`
- `source_url`
- `published_at`
- `summary`
- `raw_category`
- `scraped_at`
- `content_hash`

### Reglas de deduplicacion

- upsert por `source_name + source_url`
- deduplicacion adicional por `source_name + content_hash`
- una segunda ejecucion sobre el mismo feed no inserta duplicados

## Instalacion

1. Crear entorno virtual e instalar dependencias:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

2. Levantar PostgreSQL:

```bash
docker compose up -d postgres
```

3. Copiar variables de entorno:

```bash
copy .env.example .env
```

4. Ejecutar migraciones:

```bash
alembic upgrade head
```

5. Seed inicial de competiciones:

```bash
python scripts/seed_competitions.py
```

## Uso

Ejecutar Futbolme partidos:

```bash
python -m app.pipelines.run_source --source futbolme --competition division_honor_mallorca --target matches
python -m app.pipelines.run_source --source futbolme --competition tercera_rfef_g11 --target matches
python -m app.pipelines.run_source --source futbolme --competition segunda_rfef_g3_baleares --target matches
```

Ejecutar Futbolme clasificacion:

```bash
python -m app.pipelines.run_source --source futbolme --competition division_honor_mallorca --target standings
python -m app.pipelines.run_source --source futbolme --competition tercera_rfef_g11 --target standings
python -m app.pipelines.run_source --source futbolme --competition segunda_rfef_g3_baleares --target standings
```

Ejecutar noticias RSS:

```bash
python -m app.pipelines.run_source --source diario_mallorca --target news
python -m app.pipelines.run_source --source ultima_hora --target news
```

Modo `dry-run`:

```bash
python -m app.pipelines.run_source --source futbolme --competition division_honor_mallorca --target matches --dry-run
```

Pipeline diario:

```bash
python -m app.pipelines.run_daily
```

## Explotacion de datos

La CLI de lectura vive en `app/pipelines/query_competition.py` y consulta la base ya ingerida.

Ejemplos:

```bash
python -m app.pipelines.query_competition latest-results --competition division_honor_mallorca --limit 5
python -m app.pipelines.query_competition latest-results --competition tercera_rfef_g11 --limit 5
python -m app.pipelines.query_competition latest-results --competition segunda_rfef_g3_baleares --limit 5 --relevant-only
python -m app.pipelines.query_competition standings --competition division_honor_mallorca
python -m app.pipelines.query_competition standings --competition tercera_rfef_g11
python -m app.pipelines.query_competition standings --competition segunda_rfef_g3_baleares
python -m app.pipelines.query_competition upcoming --competition division_honor_mallorca --limit 5
python -m app.pipelines.query_competition upcoming --competition tercera_rfef_g11 --limit 5
python -m app.pipelines.query_competition upcoming --competition segunda_rfef_g3_baleares --limit 5 --relevant-only
python -m app.pipelines.query_competition round --competition division_honor_mallorca --round-name 25
python -m app.pipelines.query_competition round --competition segunda_rfef_g3_baleares --round-name 27 --relevant-only
python -m app.pipelines.query_competition top-attack --competition division_honor_mallorca --limit 5
python -m app.pipelines.query_competition top-defense --competition division_honor_mallorca --limit 5
python -m app.pipelines.query_competition most-wins --competition division_honor_mallorca --limit 5
python -m app.pipelines.query_competition window --competition division_honor_mallorca --window today
python -m app.pipelines.query_competition window --competition segunda_rfef_g3_baleares --window today --relevant-only
python -m app.pipelines.query_competition window --competition division_honor_mallorca --window tomorrow
python -m app.pipelines.query_competition window --competition division_honor_mallorca --window next_weekend
python -m app.pipelines.query_competition summary --competition division_honor_mallorca
```

Consultas disponibles:

- ultimos resultados
- clasificacion actual
- proximos partidos
- partidos por jornada
- equipos con mas goles a favor
- equipos con menos goles en contra
- equipos con mas victorias
- partidos de hoy, manana y proximo fin de semana
- resumen agregado de la competicion

Tambien hay ejemplos SQL en `scripts/example_queries.sql`.

## Explotacion de noticias

La CLI de lectura vive en `app/pipelines/query_news.py` y consulta la tabla `news` ya ingerida.

Ejemplos:

```bash
python -m app.pipelines.query_news latest --limit 10
python -m app.pipelines.query_news today
python -m app.pipelines.query_news source --source diario_mallorca --limit 10
python -m app.pipelines.query_news source --source ultima_hora --limit 10
python -m app.pipelines.query_news search --text mallorca --limit 10
```

Consultas disponibles:

- ultimas noticias
- noticias de hoy
- noticias por fuente
- busqueda simple por texto en titular

## Capa editorial de noticias

La capa editorial vive sobre `news` mediante una tabla separada `news_enrichments`, para no mezclar la noticia cruda con inferencias de relevancia.

### Modelo editorial persistido

Por cada noticia se calcula y guarda:

- `sport_detected`
- `is_football`
- `is_balearic_related`
- `clubs_detected`
- `competition_detected`
- `editorial_relevance_score`

### Fuente de reglas

La clasificacion se basa en reglas y diccionarios configurables en:

- `app/config/editorial_rules.json`
- `app/config/team_aliases.json`
- `app/config/competitions.json`

La deteccion de clubs combina:

- clubes baleares prioritarios definidos a mano
- alias manuales
- nombres completos de equipos ya almacenados en la BD

### Formula de scoring

La formula actual suma y resta puntos con reglas simples:

- `+6` si la noticia se clasifica como futbol
- `+4` si aparecen terminos de futbol
- `+8` si aparece al menos un club balear detectado
- `+2` por cada club adicional detectado
- `+6` si aparece una competicion objetivo
- `+3` si aparecen terminos geograficos baleares
- `-8` si el deporte detectado es otro no futbolistico
- `-4` si aparecen terminos penalizados de otros deportes y no domina el futbol
- `-6` si no aparece ninguna senal balear

La relevancia editorial practica no depende solo del score:

- `relevante para futbol balear`: `is_football=true` e `is_balearic_related=true`
- `futbol no balear`: `is_football=true` e `is_balearic_related=false`
- `otros deportes`: `is_football=false`

### CLI editorial

Primero ejecutar el enriquecimiento:

```bash
python -m app.pipelines.editorial_news enrich
```

Luego consultar:

```bash
python -m app.pipelines.editorial_news relevant --limit 20
python -m app.pipelines.editorial_news non-balearic --limit 20
python -m app.pipelines.editorial_news club --club "Real Mallorca" --limit 20
python -m app.pipelines.editorial_news competition --competition "3a RFEF Grupo 11" --limit 20
python -m app.pipelines.editorial_news top --limit 20
python -m app.pipelines.editorial_news summary
```

### Limitaciones actuales

- La capa es deliberadamente determinista y basada en reglas; no intenta resolver ambiguedad semantica compleja.
- Algunos titulares breves o ironicos pueden quedar como `other` aunque sean futbol.
- La deteccion de competicion depende mucho de que el titular o resumen use palabras cercanas al diccionario configurado.
- `futsal` se considera deporte distinto de `football` en esta capa editorial.

## Motor de resumen editorial

La primera pieza real del motor editorial vive en `app/services/editorial_summary.py`. No genera todavia copy final para redes ni textos largos, sino una salida estructurada y reutilizable para alimentar:

- plantillas de contenido
- prompts de redaccion
- colas editoriales
- dashboards internos

La CLI de acceso vive en `app/pipelines/editorial_summary.py` y combina:

- estado de competicion desde `matches` y `standings`
- rankings y ventanas de calendario desde la capa de consulta de competicion
- noticias relevantes desde `news` + `news_enrichments`

En competiciones con `tracked_teams`, el resumen editorial filtra por defecto los partidos y ventanas a la capa relevante de uFutbolBalear, pero conserva clasificacion y rankings del grupo completo.

### Estructura del resumen

El esquema Pydantic de salida se define en `app/schemas/editorial_summary.py` e incluye:

- `metadata`
- `competition_state`
- `latest_results`
- `upcoming_matches`
- `current_standings`
- `rankings`
- `calendar_windows`
- `editorial_news`
- `aggregate_metrics`

### Priorizacion de noticias dentro del resumen

La seleccion editorial para una competicion sigue este orden:

1. noticias con `competition_detected` igual a la competicion o sus alias
2. noticias con `clubs_detected` que encajan con equipos de la competicion
3. noticias de contexto general de futbol balear si no hay suficiente senal directa

Cada noticia incluida en el resumen lleva `selection_reason`:

- `competition_detected`
- `club_overlap`
- `general_context`

### CLI del resumen editorial

Ejemplos:

```bash
python -m app.pipelines.editorial_summary competition --competition division_honor_mallorca
python -m app.pipelines.editorial_summary competition --competition tercera_rfef_g11
python -m app.pipelines.editorial_summary competition --competition segunda_rfef_g3_baleares
python -m app.pipelines.editorial_summary competition --competition division_honor_mallorca --reference-date 2026-03-14
python -m app.pipelines.editorial_summary competition --competition tercera_rfef_g11 --reference-date 2026-03-14
python -m app.pipelines.editorial_summary competition --competition segunda_rfef_g3_baleares --reference-date 2026-03-14
python -m app.pipelines.editorial_summary competition --competition division_honor_mallorca --output json
python -m app.pipelines.editorial_summary competition --competition segunda_rfef_g3_baleares --full-group
python -m app.pipelines.editorial_summary competition --competition division_honor_mallorca --news-limit 10 --results-limit 5 --upcoming-limit 5 --standings-limit 5
```

### Ejemplo de salida en consola

```text
Resumen Editorial | Division Honor Mallorca (division_honor_mallorca)
reference_date=2026-03-14
generated_at=2026-03-14T...

Estado General
- total_teams=18
- total_matches=306
- played_matches=216
- pending_matches=90

Ultimos Resultados
- Jornada 24 | sabado, 07 de marzo de 2026 | 0-1 | Platges Calvia B vs CD Atl Rafal | finished
...

Noticias Editoriales Relevantes
- 2026-03-14T06:01:47+01:00 | score=21 | motivo=general_context | competicion=- | clubs=Real Mallorca | El Mallorca encara ante el Espanyol un punto de inflexion para todos
...
```

### Limitaciones actuales del resumen editorial

- Si no hay noticias directas de la competicion, el resumen rellena la seccion editorial con contexto general de futbol balear segun score y relevancia.
- La salida estructurada esta pensada como capa intermedia. No intenta redactar narrativa final ni tono editorial.
- El resumen depende del estado actual de la BD; no mantiene todavia snapshots historicos de clasificacion ni de noticias por ventana de publicacion preparada para newsletter.

## Generador de borradores editoriales

La siguiente capa del motor editorial vive en `app/services/editorial_content_generator.py`. Consume `editorial_summary` y genera borradores estructurados listos para revision, sin usar LLM ni publicar nada.

### Tipos de contenido generados

- `match_result`
- `standings`
- `preview`
- `ranking`
- `stat_narrative`
- `metric_narrative`

### Tabla `content_candidates`

La salida se persiste en `content_candidates` con esta estructura:

- `id`
- `competition_slug`
- `content_type`
- `priority`
- `text_draft`
- `payload_json`
- `source_summary_hash`
- `created_at`
- `updated_at`
- `scheduled_at`
- `status`

Estados disponibles:

- `draft`
- `approved`
- `rejected`
- `published`

`source_summary_hash` es un hash determinista del fragmento del resumen que alimenta cada borrador. Eso permite:

- no duplicar candidatos cuando se ejecuta dos veces el mismo resumen
- actualizar un borrador `draft` si cambia la plantilla pero no cambia la fuente del contenido
- crear un nuevo candidato cuando cambia de verdad el dato fuente

### Conexion con `editorial_summary`

Flujo actual:

1. `CompetitionEditorialSummaryService` construye el resumen estructurado.
2. `EditorialContentGenerator` aplica plantillas por tipo de contenido.
3. `ContentCandidateRepository` guarda los borradores en `content_candidates`.

### CLI del generador

El acceso vive en `app/pipelines/generate_content.py`.

Ejemplos:

```bash
python -m app.pipelines.generate_content --competition division_honor_mallorca
python -m app.pipelines.generate_content --competition tercera_rfef_g11
python -m app.pipelines.generate_content --competition segunda_rfef_g3_baleares
python -m app.pipelines.generate_content --competition segunda_rfef_g3_baleares --full-group
python -m app.pipelines.generate_content --competition tercera_rfef_g11 --output json
```

### Ejemplo de borradores

```text
RESULTADO FINAL

CD Llosetense 3-0 SD Portmany

3a RFEF Grupo 11
Jornada 25
Estado: finished
```

```text
NARRATIVA ESTADISTICA

En 3a RFEF Grupo 11 se han marcado 637 goles en 223 partidos jugados, con una media de 2.95 por encuentro.
```

### Limitaciones actuales del generador

- Solo usa plantillas deterministas; no intenta redactar tono periodistico sofisticado.
- No publica ni integra APIs externas.
- No resuelve todavia colas editoriales, aprobacion ni scheduling automatico.
- Las piezas dependen directamente del resumen actual; no hay historico editorial versionado por campaña.

## Planning editorial semanal

La capa de planning vive desacoplada en:

- `app/config/editorial_schedule.json`
- `app/core/editorial_schedule.py`
- `app/services/editorial_planner.py`
- `app/pipelines/editorial_planner.py`

Su papel es operativo, no editorial:

- define que combinaciones conviene generar cada dia
- no sustituye `editorial_summary`
- no cambia el motor de plantillas
- no aprueba ni publica nada
- ordena la operativa semanal para que el flujo humano sea repetible

### Estructura del planning semanal

El fichero `app/config/editorial_schedule.json` usa una estructura de semana con reglas por dia:

```json
{
  "timezone": "Europe/Madrid",
  "weekly_plan": {
    "lunes": [
      {
        "competition_slug": "tercera_rfef_g11",
        "content_type": "latest_results",
        "priority": 100
      },
      {
        "competition_slug": "tercera_rfef_g11",
        "content_type": "standings",
        "priority": 80
      },
      {
        "competition_slug": "segunda_rfef_g3_baleares",
        "content_type": "latest_results",
        "priority": 100
      },
      {
        "competition_slug": "segunda_rfef_g3_baleares",
        "content_type": "standings",
        "priority": 80
      },
      {
        "competition_slug": "division_honor_mallorca",
        "content_type": "latest_results",
        "priority": 95
      },
      {
        "competition_slug": "division_honor_mallorca",
        "content_type": "standings",
        "priority": 75
      }
    ],
    "miercoles": [
      {
        "competition_slug": "tercera_rfef_g11",
        "content_type": "ranking",
        "priority": 70
      },
      {
        "competition_slug": "tercera_rfef_g11",
        "content_type": "metric_narrative",
        "priority": 68
      },
      {
        "competition_slug": "segunda_rfef_g3_baleares",
        "content_type": "stat_narrative",
        "priority": 65
      },
      {
        "competition_slug": "segunda_rfef_g3_baleares",
        "content_type": "metric_narrative",
        "priority": 68
      }
    ],
    "viernes": [
      {
        "competition_slug": "segunda_rfef_g3_baleares",
        "content_type": "preview",
        "priority": 90
      }
    ]
  }
}
```

Campos soportados por regla:

- `competition_slug`
- `content_type`
- `priority`

Tipos de planning soportados:

- `latest_results`
- `standings`
- `preview`
- `ranking`
- `stat_narrative`
- `metric_narrative`

Mapeo interno:

- `latest_results` genera candidatos `match_result`
- `standings` genera candidatos `standings`
- `preview` genera candidatos `preview`
- `ranking` genera candidatos `ranking`
- `stat_narrative` genera candidatos `stat_narrative`
- `metric_narrative` genera candidatos `metric_narrative`

### Servicio y comportamiento

`EditorialPlannerService` puede:

- leer el planning semanal
- resolver que tareas tocan para una fecha dada
- generar un campaign plan estructurado
- listar tareas editoriales del dia
- lanzar la generacion de `content_candidates` solo para las combinaciones previstas ese dia
- validar explicitamente que cada resumen y cada candidato pertenecen a la competicion pedida

La planificacion queda separada de:

- `editorial_summary`
- generacion de contenido
- cola editorial
- exportacion a Typefully

### CLI del planner

```bash
python -m app.pipelines.editorial_planner today
python -m app.pipelines.editorial_planner date --date 2026-03-16
python -m app.pipelines.editorial_planner week
python -m app.pipelines.editorial_planner generate-today
python -m app.pipelines.editorial_planner generate-date --date 2026-03-16
```

### Ejemplo de salida de `today`

```text
Plan Editorial | 2026-03-15 (domingo)
total_tasks=2

- priority=100 | competition=3a RFEF Grupo 11 (tercera_rfef_g11) | content=latest_results | target=match_result
- priority=100 | competition=2a RFEF Grupo 3 (segunda_rfef_g3_baleares) | content=latest_results | target=match_result
```

### Ejemplo de `generate-today`

```text
Generacion Planificada | 2026-03-15 (domingo)
total_tasks=2
total_generated=4
total_inserted=4
total_updated=0

- priority=100 | tercera_rfef_g11 | latest_results -> match_result | selected=2 | inserted=2 | updated=0
- priority=100 | segunda_rfef_g3_baleares | latest_results -> match_result | selected=2 | inserted=2 | updated=0
```

### Flujo operativo recomendado

1. actualizar scraping y datos base de competiciones
2. revisar `python -m app.pipelines.editorial_planner today`
3. generar borradores planificados con `generate-today` o `generate-date`
4. opcionalmente refinar piezas con `editorial_rewrite`
5. revisar la cola editorial manual
6. despachar internamente y exportar a Typefully cuando proceda

### Limitaciones actuales del planning

- no persiste una entidad separada de campaÃ±a; resuelve reglas y genera candidatos al vuelo
- no detecta colisiones de agenda ni duplica reglas con logica avanzada
- no programa aprobaciones ni exportaciones automaticas
- depende de que la competicion exista en catalogo y tenga datos ya ingeridos en BD

## Readiness y operativa diaria

La capa operativa real se apoya en:

- `app/services/competition_catalog_service.py`
- `app/services/system_check.py`
- `app/services/editorial_ops.py`
- `app/pipelines/competition_catalog.py`
- `app/pipelines/system_check.py`
- `app/pipelines/editorial_ops.py`

### Checklist de readiness

Antes de generar piezas en la BD real conviene ejecutar:

```bash
python -m app.pipelines.competition_catalog status --integrated-only
python -m app.pipelines.system_check editorial-readiness
```

Si una competicion integrada falta en la tabla `competitions`, se puede sembrar con:

```bash
python -m app.pipelines.competition_catalog seed --integrated-only --missing-only
```

`editorial-readiness` comprueba al menos:

- competiciones integradas presentes en catalogo y en BD
- recuento real de `matches`, `finished_matches`, `scheduled_matches` y `standings`
- si cada competicion tiene datos suficientes para el planning semanal configurado
- si Typefully esta configurado
- cuantos `content_candidates` existen y cuantos siguen pendientes de exportacion

### Vista previa operativa

Para ver que se generaria un dia concreto sin tocar la BD:

```bash
python -m app.pipelines.editorial_ops preview-day --date 2026-03-16
python -m app.pipelines.editorial_ops preview-day --date 2026-03-18
```

La salida indica:

- competiciones incluidas ese dia
- `planning_type` y `target_content_type`
- cuantas piezas se esperan aproximadamente
- dependencias bloqueantes si faltan datos

Ejemplo:

```text
Preview Day | 2026-03-18
total_tasks=4
ready_tasks=4
blocked_tasks=0
expected_total=14

- priority=70 | tercera_rfef_g11 | ranking -> ranking | expected=1 | missing=-
- priority=68 | segunda_rfef_g3_baleares | metric_narrative -> metric_narrative | expected=6 | missing=-
- priority=68 | tercera_rfef_g11 | metric_narrative -> metric_narrative | expected=6 | missing=-
- priority=65 | segunda_rfef_g3_baleares | stat_narrative -> stat_narrative | expected=1 | missing=-
```

### Ejecucion diaria real

Para persistir los candidatos previstos por el planning:

```bash
python -m app.pipelines.editorial_ops run-daily --date 2026-03-16
python -m app.pipelines.editorial_ops run-daily --date 2026-03-18
```

`run-daily`:

- resuelve el planning de la fecha
- genera `content_candidates` solo para tareas listas
- persiste piezas nuevas o actualiza borradores existentes
- no aprueba ni exporta nada automaticamente

Ejemplo:

```text
Run Daily | 2026-03-16
total_tasks=6
generated_total=18
inserted_total=0
updated_total=15
blocked_tasks=0
```

### Flujo diario recomendado

1. comprobar catalogo y readiness
2. ejecutar `preview-day` para la fecha objetivo
3. ejecutar `run-daily` para persistir los borradores previstos
4. revisar la cola editorial con `editorial_queue`
5. aprobar manualmente las piezas que salgan
6. despachar internamente con `publication_dispatch`
7. exportar a Typefully las piezas `published`

## Narrativas metricas editoriales

La capa de narrativas metricas vive en:

- `app/services/editorial_narratives.py`
- `app/pipelines/editorial_narratives.py`

Su funcion es detectar piezas sociales breves basadas en datos reales ya persistidos en la BD. No usa IA para calcular metricas.

### Narrativas soportadas

- `win_streak`: victorias consecutivas actuales de un equipo
- `unbeaten_streak`: partidos seguidos sin perder
- `best_attack`: equipo con mas goles a favor
- `best_defense`: equipo con menos goles encajados
- `most_wins`: equipo con mas victorias
- `goals_average`: media de goles por partido de la competicion

`equipo revelacion` queda diferido hasta tener una definicion mas robusta.

### Como se calculan

- `win_streak`: se recorre la serie de partidos finalizados mas recientes por equipo y se cuenta hasta el primer no-triunfo; se publica si la racha actual es de al menos `3`
- `unbeaten_streak`: mismo recorrido, contando victorias o empates hasta la primera derrota; se publica si la racha actual es de al menos `4`
- `best_attack`, `best_defense`, `most_wins`: salen de la clasificacion actual almacenada en `standings`
- `goals_average`: se calcula con todos los partidos `finished` de la competicion y su total de goles real

Las plantillas son deterministas, limpias y sin exageracion. El texto sale apto para Typefully/X, pero sin convertir la metrica en opinion.

### CLI de narrativas

```bash
python -m app.pipelines.editorial_narratives show --competition tercera_rfef_g11
python -m app.pipelines.editorial_narratives generate --competition tercera_rfef_g11
python -m app.pipelines.editorial_narratives generate --competition segunda_rfef_g3_baleares
```

### Ejemplos de narrativas

```text
CD Llosetense suma 3 victorias consecutivas en 3a RFEF Baleares.
CD Llosetense encadena 4 partidos sin perder en 3a RFEF Baleares.
CD Llosetense firma el mejor ataque de 3a RFEF Baleares con 24 goles a favor.
En 3a RFEF Baleares se marcan 2.25 goles por partido tras 4 encuentros disputados.
```

### Integracion con el planner

La integracion queda resuelta via `content_type=metric_narrative` en el planning semanal. Ejemplo operativo:

- miercoles: `tercera_rfef_g11 -> ranking + metric_narrative`
- miercoles: `segunda_rfef_g3_baleares -> stat_narrative + metric_narrative`
- lunes: `division_honor_mallorca -> latest_results + standings`

Eso permite combinar:

- bloques editoriales estructurados (`ranking`, `standings`, `preview`)
- piezas sociales cortas y reutilizables (`metric_narrative`)

### Recorrido completo de `metric_narrative`

Las narrativas metricas no tienen un flujo especial. Recorren el mismo circuito que cualquier otro `content_candidate`:

1. `editorial_ops run-daily --date 2026-03-18`
2. `editorial_queue approve --id <ID>`
3. `publication_dispatch dispatch --include-unscheduled`
4. `typefully_export dry-run --id <ID>`
5. `typefully_export export --id <ID>`

## Historias virales editoriales

La capa de historias virales vive en:

- `app/services/editorial_viral_stories.py`
- `app/pipelines/editorial_viral_stories.py`

Su objetivo es detectar relatos destacados con potencial social usando solo datos reales de BD. La deteccion es determinista; la IA no interviene en el calculo.

### Historias soportadas

- `win_streak`: racha actual de victorias
- `unbeaten_streak`: racha actual sin perder
- `losing_streak`: racha negativa actual
- `best_attack`: mejor ataque con ventaja suficiente sobre el segundo
- `best_defense`: mejor defensa con margen claro
- `recent_top_scorer`: equipo mas goleador en su tramo reciente
- `hot_form`: equipo con mejor forma reciente por puntos
- `cold_form`: equipo en mala dinamica reciente
- `goals_trend`: tendencia ofensiva o defensiva de la competicion

Historias diferidas por ahora:

- cambio de liderato o puestos clave: no hay historico robusto de clasificacion por fecha
- equipo revelacion: falta una definicion estable con el modelo actual

### Como se calculan

- `win_streak`: minimo `3` victorias consecutivas
- `unbeaten_streak`: minimo `4` partidos sin perder
- `losing_streak`: minimo `3` derrotas consecutivas
- `hot_form`: al menos `10` puntos en los ultimos `5` partidos
- `cold_form`: `3` puntos o menos y al menos `3` derrotas en los ultimos `5` partidos
- `recent_top_scorer`: lider reciente con al menos `5` goles en sus ultimos `3` partidos y margen minimo de `2`
- `best_attack`, `best_defense`: salen de `standings` y requieren una ventaja minima de `2` respecto al segundo registro
- `goals_trend`: compara la media reciente de la competicion con la media de toda la temporada y dispara con un diferencial absoluto de al menos `0.6`

### CLI de historias virales

```bash
python -m app.pipelines.editorial_viral_stories show --competition tercera_rfef_g11
python -m app.pipelines.editorial_viral_stories generate --competition tercera_rfef_g11
python -m app.pipelines.editorial_viral_stories generate --competition segunda_rfef_g3_baleares
```

### Ejemplos de historias

```text
CD Llosetense firma 10 de 12 puntos en sus ultimos 4 partidos de 3a RFEF Baleares.
CD Llosetense es el equipo mas goleador en sus ultimos 3 partidos de 3a RFEF Baleares: 6 tantos.
UE Porreres arrastra 3 derrotas consecutivas en 2a RFEF con equipos baleares.
3a RFEF Baleares deja una tendencia ofensiva reciente: 4.2 goles por partido en los ultimos 5 encuentros.
```

### Integracion con el planner

El planner semanal incorpora un bloque especifico de `viral_story` en miercoles:

- `tercera_rfef_g11 -> ranking + viral_story + metric_narrative`
- `segunda_rfef_g3_baleares -> stat_narrative + viral_story + metric_narrative`

Las `viral_story` recorren el mismo circuito que cualquier otro `content_candidate`: generacion, review, dispatch y exportacion a canal. Por politica editorial, su salida a Typefully sigue siendo manual salvo cambio explicito de config.

## Reescritura editorial opcional con LLM

La capa de reescritura vive en `app/services/editorial_rewriter.py` y se expone por CLI en `app/pipelines/editorial_rewrite.py`.

Su papel es deliberadamente acotado:

- no calcula datos
- no decide que pieza generar
- no sustituye plantillas ni reglas
- no publica nada
- solo refina el texto final de `text_draft` si se solicita

El centro sigue siendo `content_candidates`. La capa LLM opera por encima y deja el texto base intacto.

### Persistencia en `content_candidates`

La reescritura se guarda en campos separados:

- `rewritten_text`
- `rewrite_status`
- `rewrite_model`
- `rewrite_timestamp`
- `rewrite_error`

Esto permite comparar siempre:

- `text_draft`: borrador base determinista del sistema
- `rewritten_text`: version refinada por LLM, opcional

Si el borrador base cambia en una regeneracion posterior mientras la pieza sigue en `draft`, la reescritura anterior se limpia automaticamente para evitar mezclar versiones.

### Politica editorial aplicada al prompt

La politica de reescritura impone:

- mantener exactos todos los datos del borrador y de `payload_json`
- no inventar contexto, antecedentes, opiniones ni hype
- no recalcular cifras ni corregir datos con conocimiento externo
- tono directo, periodistico y limpio
- texto breve y apto para Typefully/X
- maximo configurable de caracteres
- estilo de marca uFutbolBalear sin emojis ni hashtags

Ademas, hay guias especificas por tipo:

- `match_result`
- `standings`
- `preview`
- `ranking`
- `stat_narrative`
- `viral_story`

### Proveedor y configuracion

La estructura queda preparada para cambiar de proveedor sin tocar la logica editorial. La implementacion inicial usa un adaptador OpenAI via Responses API.

Variables de entorno:

```bash
EDITORIAL_REWRITE_PROVIDER=openai
EDITORIAL_REWRITE_API_KEY=...
EDITORIAL_REWRITE_API_URL=https://api.openai.com/v1/responses
EDITORIAL_REWRITE_MODEL=...
EDITORIAL_REWRITE_MAX_CHARS=280
```

Notas:

- `EDITORIAL_REWRITE_PROVIDER`: hoy soporta `openai`
- `EDITORIAL_REWRITE_API_KEY`: obligatoria para modo real
- `EDITORIAL_REWRITE_API_URL`: por defecto `https://api.openai.com/v1/responses`
- `EDITORIAL_REWRITE_MODEL`: obligatorio para modo real
- `EDITORIAL_REWRITE_MAX_CHARS`: limita la salida final y por defecto queda en `280`

### Elegibilidad para reescritura

Una pieza es elegible si:

- existe `content_candidate`
- `text_draft` no esta vacio
- `status` esta en `draft`, `approved` o `published`
- no existe `rewritten_text`, salvo que se use `overwrite`

No se reescriben:

- candidatos inexistentes
- candidatos con `text_draft` vacio
- candidatos en `rejected`
- candidatos con `rewritten_text` ya persistido si no se pasa `overwrite`

### CLI de reescritura

```bash
python -m app.pipelines.editorial_rewrite show --id 19
python -m app.pipelines.editorial_rewrite dry-run --id 19
python -m app.pipelines.editorial_rewrite rewrite --id 19
python -m app.pipelines.editorial_rewrite rewrite --id 19 --overwrite
python -m app.pipelines.editorial_rewrite rewrite-pending --limit 10
python -m app.pipelines.editorial_rewrite rewrite-pending --limit 10 --dry-run
```

### Dry-run y modo real

`dry-run`:

- valida elegibilidad
- no persiste cambios
- si el proveedor esta configurado, pide una propuesta real al LLM
- si el proveedor no esta configurado, sigue funcionando con una vista previa local que deja `text_draft` intacto y marca `rewrite_status=dry_run_unconfigured`

`rewrite`:

- ejecuta la llamada real al proveedor
- persiste `rewritten_text` y trazabilidad
- guarda `rewrite_status=failed` y `rewrite_error` si el proveedor falla

### Ejemplo base vs reescrito

Base:

```text
RESULTADO FINAL

Torrent CF 1-0 UE Porreres

2a RFEF Grupo 3
Jornada 26
Estado: finished
```

Reescrito:

```text
Torrent CF se impuso por 1-0 a la UE Porreres en la jornada 26 de la 2a RFEF Grupo 3.
```

### Relacion con Typefully y X

- `typefully_export` sigue usando `text_draft`
- `x_publish` sigue usando `text_draft`
- `rewritten_text` no se usa automaticamente en ningun canal
- la arquitectura queda preparada para que en el futuro un canal pueda elegir explicitamente entre `text_draft` y `rewritten_text`

### Limitaciones actuales de la reescritura

- la verificacion de exactitud depende de instrucciones y validaciones basicas; no hay chequeo semantico fuerte de todos los hechos
- hoy solo hay proveedor `openai`, aunque el servicio ya queda desacoplado
- no se persiste aun una auditoria completa del prompt ni del raw response fuera del adaptador
- la salida debe caber en `EDITORIAL_REWRITE_MAX_CHARS`; si el modelo se pasa, la reescritura falla
- si no hay credenciales del proveedor, el modo real no puede validarse; en ese caso el entorno sigue siendo util con `dry-run` y tests con mocks

## Cola editorial manual

La capa operativa de revision vive en `app/services/editorial_queue.py` y se expone por CLI en `app/pipelines/editorial_queue.py`.

Se apoya sobre `content_candidates` pero no se mezcla con la generacion: la generacion crea borradores y la cola decide su revision, programacion y cierre manual.

### Campos operativos adicionales

La tabla `content_candidates` queda preparada con:

- `reviewed_at`
- `approved_at`
- `published_at`
- `rejection_reason`
- `external_publication_ref`

### Transiciones soportadas

- `draft -> approved`
- `draft -> rejected`
- `approved -> draft`
- `approved -> rejected`
- `approved -> published`
- `rejected -> draft`

Restricciones actuales:

- `published` se trata como estado final
- no se puede programar un candidato `rejected` o `published`

### CLI de la cola editorial

```bash
python -m app.pipelines.editorial_queue list --status draft
python -m app.pipelines.editorial_queue list --competition tercera_rfef_g11
python -m app.pipelines.editorial_queue list --content-type preview
python -m app.pipelines.editorial_queue show --id 12
python -m app.pipelines.editorial_queue approve --id 12
python -m app.pipelines.editorial_queue reject --id 12 --reason "duplicado"
python -m app.pipelines.editorial_queue reset --id 12
python -m app.pipelines.editorial_queue publish --id 12
python -m app.pipelines.editorial_queue schedule --id 12 --scheduled-at 2026-03-15T10:00:00+01:00
python -m app.pipelines.editorial_queue summary
```

### Flujo manual recomendado

1. generar borradores con `generate_content`
2. listar la cola en `draft`
3. revisar detalle con `show`
4. aprobar o rechazar
5. programar `scheduled_at` cuando proceda
6. marcar como `published` solo cuando la salida haya sido realmente difundida por la capa externa futura

### Limitaciones actuales de la cola

- no hay todavia interfaz web; la operativa es solo por CLI
- no hay asignacion de usuarios ni `reviewed_by`

## Dispatcher de publicacion

La capa de despacho vive en `app/services/publication_dispatcher.py` y se expone por CLI en `app/pipelines/publication_dispatch.py`.

Su papel es distinto al de la cola:

- la cola editorial revisa y aprueba
- el dispatcher decide si una pieza aprobada ya esta lista para salir
- el dispatcher solo marca `published` internamente; no conecta con Twitter/X ni Telegram

### Elegibilidad exacta

Una pieza se considera elegible para publicacion si:

- `status = approved`
- `published_at IS NULL`
- `scheduled_at <= now`

En modo manual tambien puede listarse o publicarse una pieza `approved` sin `scheduled_at`.

No son elegibles:

- `draft`
- `rejected`
- `published`
- `approved` con `scheduled_at` futuro en dispatch automatico

### CLI del dispatcher

```bash
python -m app.pipelines.publication_dispatch list-ready
python -m app.pipelines.publication_dispatch list-ready --now 2026-03-15T10:00:00+01:00
python -m app.pipelines.publication_dispatch dispatch --dry-run
python -m app.pipelines.publication_dispatch dispatch --limit 5
python -m app.pipelines.publication_dispatch dispatch --now 2026-03-15T10:00:00+01:00
python -m app.pipelines.publication_dispatch publish --id 19
python -m app.pipelines.publication_dispatch summary
```

### Diferencia entre cola y dispatch

- `editorial_queue`: gestiona revision, aprobacion, rechazo y programacion
- `publication_dispatch`: selecciona piezas aprobadas listas para salir y las marca como `published`

### Limitaciones actuales del dispatcher

- no hay reintentos, auditoria de canal ni rollback multi-canal
- `published` sigue significando despacho interno, no confirmacion externa de canal

## Publicacion en X

La integracion de X vive desacoplada en:

- `app/channels/x/auth.py`
- `app/channels/x/client.py`
- `app/channels/x/publisher.py`
- `app/services/x_auth_service.py`
- `app/services/x_publication_service.py`
- `app/pipelines/x_auth.py`
- `app/pipelines/x_publish.py`

La logica editorial no conoce la API de X. El flujo es:

1. la pieza pasa a `published` por el dispatcher interno
2. `x_auth` autoriza una cuenta de usuario de X mediante OAuth 2.0 Authorization Code with PKCE
3. el adaptador de X busca piezas `published` sin `external_publication_ref`
4. si la publicacion externa sale bien, guarda el id del tweet y la trazabilidad del intento

El cliente publica contra `POST https://api.x.com/2/tweets`.

### Por que PKCE

X exige contexto de usuario para `POST /2/tweets`. Si solo tienes `API Key`, `API Secret` y `Bearer Token`, eso no basta para publicar en nombre de un usuario. Por eso la ruta principal del proyecto migra a OAuth 2.0 Authorization Code with PKCE, que deja el token de usuario desacoplado del nucleo editorial.

### Configuracion necesaria

Configura estas variables de entorno:

```bash
X_CLIENT_ID=...
X_CLIENT_SECRET=
X_REDIRECT_URI=http://127.0.0.1:8000/callback
X_SCOPES=tweet.read tweet.write users.read offline.access
X_API_BASE_URL=https://api.x.com
X_AUTHORIZE_URL=https://x.com/i/oauth2/authorize
X_TOKEN_URL=https://api.x.com/2/oauth2/token
```

Variables clave:

- `X_CLIENT_ID`: obligatorio para PKCE
- `X_REDIRECT_URI`: obligatorio y debe coincidir exactamente con el configurado en la app de X
- `X_SCOPES`: por defecto `tweet.read tweet.write users.read offline.access`
- `X_CLIENT_SECRET`: opcional; solo se usa si la app esta configurada como confidential client

### Ejemplo de `.env`

```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/futbol_balear
X_CLIENT_ID=tu_client_id
X_REDIRECT_URI=http://127.0.0.1:8000/callback
X_SCOPES=tweet.read tweet.write users.read offline.access
```

### Flujo exacto de autorizacion

1. ejecutar `python -m app.pipelines.x_auth start-auth`
2. abrir la URL de autorizacion mostrada en consola
3. completar login y consentimiento en X
4. copiar la URL completa del callback recibido en `X_REDIRECT_URI`
5. ejecutar `python -m app.pipelines.x_auth exchange-code --callback-url "<FULL_CALLBACK_URL>"`
6. verificar el token con `python -m app.pipelines.x_auth verify-user-token`

El servicio:

- genera `state` y `code_verifier`
- construye la authorize URL con `code_challenge_method=S256`
- intercambia `code` por `access_token` y `refresh_token`
- guarda el token de usuario en base de datos
- refresca automaticamente el token si expira y hay `refresh_token`

### Donde se guarda el token de usuario

El token no se guarda en `content_candidates`. Se persiste de forma desacoplada en:

- `channel_auth_sessions`: guarda temporalmente `state`, `code_verifier` y expiracion del flujo PKCE
- `channel_user_tokens`: guarda `access_token`, `refresh_token`, `expires_at`, `scope`, `subject_id` y `subject_username`

### Elegibilidad para X

Una pieza es publicable en X si:

- `status = published`
- `external_publication_ref IS NULL`
- `text_draft` no esta vacio

No son publicables:

- `draft`
- `approved`
- `rejected`
- `published` que ya tenga `external_publication_ref`

### Trazabilidad persistida

Tras una publicacion correcta se guardan:

- `external_publication_ref`: id del tweet devuelto por X
- `external_channel`: `x`
- `external_exported_at`: momento local en que el candidato se exporto al canal
- `external_publication_timestamp`: timestamp local del exito
- `external_publication_attempted_at`: ultimo intento de salida
- `external_publication_error`: ultimo error, si lo hubo

### CLI de autenticacion X

```bash
python -m app.pipelines.x_auth start-auth
python -m app.pipelines.x_auth exchange-code --callback-url "http://127.0.0.1:8000/callback?state=...&code=..."
python -m app.pipelines.x_auth exchange-code --code "<AUTH_CODE>" --state "<STATE>"
python -m app.pipelines.x_auth verify-user-token
```

### CLI de publicacion X

```bash
python -m app.pipelines.x_publish show-pending
python -m app.pipelines.x_publish dry-run --id 31
python -m app.pipelines.x_publish publish --id 31
python -m app.pipelines.x_publish publish-pending
python -m app.pipelines.x_publish publish-pending --limit 5
python -m app.pipelines.x_publish publish-pending --dry-run
```

### Probar sin credenciales

El sistema queda usable sin token de usuario ya autorizado para:

- `show-pending`
- `dry-run --id ...`
- `publish-pending --dry-run`

Para probar publicacion real hace falta:

- `X_CLIENT_ID` y `X_REDIRECT_URI` validos
- completar `x_auth start-auth` y `x_auth exchange-code`
- validar con `x_auth verify-user-token`
- permisos de escritura sobre `POST /2/tweets`

### Checklist local de validacion

1. configurar `.env` con `X_CLIENT_ID`, `X_REDIRECT_URI` y `X_SCOPES`
2. ejecutar `python -m app.pipelines.x_auth start-auth`
3. completar consentimiento y copiar el callback
4. ejecutar `python -m app.pipelines.x_auth exchange-code --callback-url "<FULL_CALLBACK_URL>"`
5. ejecutar `python -m app.pipelines.x_auth verify-user-token`
6. ejecutar `python -m app.pipelines.x_publish show-pending`
7. ejecutar `python -m app.pipelines.x_publish dry-run --id 19`
8. ejecutar `python -m app.pipelines.x_publish publish --id 19`

### Limitaciones actuales de X

- el modelo actual soporta una sola referencia externa por `content_candidate`
- no hay soporte aun para hilos, media, respuestas ni borrado
- `external_publication_timestamp` refleja el momento del exito local, no una fecha canonica devuelta por X
- los tokens de usuario se guardan en BD sin cifrado a nivel de aplicacion; si necesitas mas proteccion, el siguiente paso es cifrado en columna o vault externo

## Exportacion de drafts a Typefully

La integracion de Typefully vive desacoplada en:

- `app/channels/typefully/client.py`
- `app/channels/typefully/publisher.py`
- `app/channels/typefully/schemas.py`
- `app/services/typefully_export_service.py`
- `app/pipelines/typefully_export.py`

El rol de Typefully en la arquitectura es solo de canal operativo de borradores. El flujo es:

1. `content_candidates` sigue siendo la fuente central
2. opcionalmente `editorial_rewrite` refina el texto final sin tocar los datos base
3. la cola editorial revisa y aprueba
4. el dispatcher interno marca la pieza como `published`
5. `typefully_export` crea un draft externo en Typefully
6. la revision, edicion fina y programacion final ocurre dentro de Typefully
7. la publicacion definitiva sale desde Typefully

### API elegida y decision

La integracion usa la API v2 actual de Typefully:

- `POST /v2/social-sets/{social_set_id}/drafts` para crear drafts
- `GET /v2/social-sets` para resolver el `social_set_id` cuando no se fija manualmente
- `GET /v2/me` queda encapsulado en el cliente para futuras validaciones reales

La decision es deliberada:

- la documentacion actual de Typefully marca la API v1 como deprecated
- la API v2 modela la creacion de drafts dentro de un `social_set`
- eso encaja mejor con el papel de Typefully como canal externo reversible y no como centro editorial

### Configuracion Typefully

Variables de entorno:

```bash
TYPEFULLY_API_KEY=...
TYPEFULLY_API_URL=https://api.typefully.com
TYPEFULLY_SOCIAL_SET_ID=
```

Notas:

- `TYPEFULLY_API_KEY`: obligatorio
- `TYPEFULLY_API_URL`: obligatorio
- `TYPEFULLY_SOCIAL_SET_ID`: opcional; si falta, el exportador intenta autodetectarlo via `GET /v2/social-sets`
- si Typefully devuelve varios `social_sets` y no hay `TYPEFULLY_SOCIAL_SET_ID`, la exportacion falla con un error explicito para evitar ambiguedad

### Elegibilidad para exportar a Typefully

Una pieza es exportable si:

- `status = published`
- `external_publication_ref IS NULL`
- `text_draft` no esta vacio

No se exportan:

- `draft`
- `approved`
- `rejected`
- `published` que ya tenga `external_publication_ref`

### Seleccion del texto a exportar

Por defecto la exportacion elige este orden:

1. `rewritten_text` si existe y no esta vacio
2. `text_draft` en cualquier otro caso

Fallbacks y overrides:

- si `rewritten_text` es `NULL`, se usa `text_draft`
- si `rewritten_text` existe pero esta vacio o solo tiene espacios, se usa `text_draft`
- `--use-draft` fuerza el uso de `text_draft`
- `--use-rewrite` mantiene la prioridad sobre `rewritten_text`, pero sigue cayendo a `text_draft` si la reescritura no es utilizable

La salida de CLI informa:

- `has_rewrite=true/false`
- `text_source=rewritten_text|text_draft`

### CLI Typefully

```bash
python -m app.pipelines.typefully_export verify-config
python -m app.pipelines.typefully_export show-pending
python -m app.pipelines.typefully_export show-pending --use-draft
python -m app.pipelines.typefully_export show-pending --use-rewrite
python -m app.pipelines.typefully_export dry-run --id 31
python -m app.pipelines.typefully_export dry-run --id 31 --use-draft
python -m app.pipelines.typefully_export dry-run --id 31 --use-rewrite
python -m app.pipelines.typefully_export export --id 31
python -m app.pipelines.typefully_export export --id 31 --use-draft
python -m app.pipelines.typefully_export export --id 31 --use-rewrite
python -m app.pipelines.typefully_export export-ready
python -m app.pipelines.typefully_export export-ready --limit 5
python -m app.pipelines.typefully_export export-ready --dry-run
python -m app.pipelines.typefully_export export-ready --dry-run --use-draft
python -m app.pipelines.typefully_export export-ready --dry-run --use-rewrite
```

## Autoexportacion controlada a Typefully

La autoexportacion controlada vive en:

- `app/config/typefully_autoexport.json`
- `app/core/typefully_autoexport.py`
- `app/services/editorial_quality_checks.py`
- `app/pipelines/editorial_quality_checks.py`
- `app/services/typefully_autoexport_service.py`
- `app/pipelines/typefully_autoexport.py`

No sustituye la exportacion manual. Es una capa adicional que decide que piezas `published` pueden convertirse automaticamente en draft de Typefully segun politica y quality checks deterministas.

### Politica exacta y despliegue por fases

Catalogo completo autoexportable:

- `match_result`
- `standings`
- `preview`
- `ranking`
- `stat_narrative`
- `metric_narrative`
- `viral_story`

Con validacion reforzada cuando la fase los habilita:

- `stat_narrative`
- `metric_narrative`
- `viral_story`

Despliegue progresivo:

- fase `1`: `match_result`, `standings`, `preview`, `ranking`
- fase `2`: añade `stat_narrative`, `metric_narrative`
- fase `3`: añade `viral_story`

La politica sigue siendo conservadora: los tipos narrativos solo autoexportan si pasan `editorial_quality_checks`. Si fallan, se bloquean y quedan para revision manual.

### Configuracion

Archivo: `app/config/typefully_autoexport.json`

```json
{
  "enabled": true,
  "phase": 1,
  "default_limit": 10,
  "use_rewrite_by_default": true,
  "max_text_length": 280,
  "duplicate_window_hours": 72,
  "max_line_breaks": 6,
  "max_exports_per_run": 5,
  "max_exports_per_day": null,
  "stop_on_capacity_limit": true,
  "capacity_error_codes": ["MONETIZATION_ERROR"],
  "allowed_content_types": [
    "match_result",
    "standings",
    "preview",
    "ranking",
    "stat_narrative",
    "metric_narrative",
    "viral_story"
  ],
  "manual_review_content_types": [],
  "validation_required_content_types": [
    "stat_narrative",
    "metric_narrative",
    "viral_story"
  ],
  "phases": {
    "1": {
      "allowed_content_types": ["match_result", "standings", "preview", "ranking"],
      "validation_required_content_types": []
    },
    "2": {
      "allowed_content_types": [
        "match_result",
        "standings",
        "preview",
        "ranking",
        "stat_narrative",
        "metric_narrative"
      ],
      "validation_required_content_types": ["stat_narrative", "metric_narrative"]
    },
    "3": {
      "allowed_content_types": [
        "match_result",
        "standings",
        "preview",
        "ranking",
        "stat_narrative",
        "metric_narrative",
        "viral_story"
      ],
      "validation_required_content_types": [
        "stat_narrative",
        "metric_narrative",
        "viral_story"
      ]
    }
  ]
}
```

Claves relevantes:

- `enabled`: activa o desactiva la autoexportacion real
- `phase`: fase activa de despliegue
- `default_limit`: numero maximo de piezas evaluadas por corrida
- `use_rewrite_by_default`: usa `rewritten_text` si existe; si no, cae a `text_draft`
- `max_text_length`: limite duro para texto autoexportable
- `duplicate_window_hours`: ventana de deduplicacion reciente
- `max_line_breaks`: evita textos mal formados
- `max_exports_per_run`: maximo de drafts creados por corrida
- `max_exports_per_day`: cupo diario; `null` lo desactiva
- `stop_on_capacity_limit`: si el canal alcanza cupo, se deja de intentar exportar mas piezas en esa corrida
- `capacity_error_codes`: codigos del canal que se tratan como limite de capacidad y no como error tecnico
- `phases`: define que tipos se habilitan en cada etapa
- `validation_required_content_types`: lista de tipos con checks reforzados

Cambio de fase:

- fase 1 -> produccion inicial segura
- fase 2 -> sumar narrativas metricas
- fase 3 -> sumar `viral_story`

### Quality checks

La validacion automatica ocurre antes de exportar y persiste:

- `quality_check_passed`
- `quality_check_errors`
- `quality_checked_at`

Checks soportados:

- texto no vacio
- longitud maxima
- deduplicacion reciente por hash, texto o narrativa equivalente
- coherencia de payload y equipos referenciados
- texto mal formado con saltos excesivos
- umbrales minimos en `stat_narrative`, `metric_narrative` y `viral_story`

CLI de depuracion:

```bash
python -m app.pipelines.editorial_quality_checks check --id 42
python -m app.pipelines.editorial_quality_checks check-pending
python -m app.pipelines.editorial_quality_checks dry-run --date 2026-03-20
```

### CLI de autoexportacion

```bash
python -m app.pipelines.typefully_autoexport status
python -m app.pipelines.typefully_autoexport pending-capacity
python -m app.pipelines.typefully_autoexport dry-run
python -m app.pipelines.typefully_autoexport dry-run --date 2026-03-18
python -m app.pipelines.typefully_autoexport dry-run --use-draft
python -m app.pipelines.typefully_autoexport run
python -m app.pipelines.typefully_autoexport run --date 2026-03-18
python -m app.pipelines.typefully_autoexport run --use-rewrite
```

Semantica de `--date`:

- filtra por `published_at` en la fecha local indicada
- permite separar un slot editorial concreto del resto de pendientes historicos

`status` muestra:

- `enabled`
- `phase`
- tipos activos en la fase
- tipos que exigen validacion
- ultimo run persistido en `logs/typefully_autoexport_status.json`

### Ejemplo de dry-run

```text
AUTOEXPORT phase=1 scanned=10 eligible=10 exported=5 blocked=0 capacity_deferred=5 failed=0
executed_at=2026-03-20T10:20:00+00:00
dry_run=true
policy_enabled=true
phase=1
reference_date=2026-03-18
scanned_count=10
eligible_count=10
exported_count=5
blocked_count=0
capacity_deferred_count=5
failed_count=0
capacity_limit_reached=true
capacity_limit_reason=capacity_deferred:max_exports_per_run
```

### Ejemplo de status

```text
enabled=true
phase=1
max_exports_per_run=5
max_exports_per_day=-
stop_on_capacity_limit=true
capacity_error_codes=MONETIZATION_ERROR
allowed_content_types=match_result, standings, preview, ranking
validation_required_content_types=-
manual_review_content_types=-
pending_capacity_count=10
pending_normal_count=0
last_execution=2026-03-20T10:20:00+00:00
last_dry_run=true
last_reference_date=2026-03-20
last_capacity_limit_reached=true
last_capacity_limit_reason=capacity_deferred:MONETIZATION_ERROR
last_summary=AUTOEXPORT phase=1 scanned=10 eligible=10 exported=5 blocked=0 capacity_deferred=5 failed=0
```

### Capacidad del canal

Si Typefully devuelve `MONETIZATION_ERROR` o el lote alcanza `max_exports_per_run`, el sistema trata esas piezas como `capacity_deferred`:

- siguen siendo reintentables
- no pierden elegibilidad
- no incrementan `failed_count`
- aparecen en `pending-capacity`
- quedan diferenciadas de bloqueos editoriales y de errores tecnicos reales

### Trazabilidad

La autoexportacion reutiliza la misma persistencia que `typefully_export`:

- `external_publication_ref`
- `external_channel=typefully`
- `external_exported_at`
- `external_publication_attempted_at`
- `external_publication_error`

Si la politica bloquea una pieza, no se toca nada en BD. Si la pieza se difiere por capacidad, `external_publication_ref` sigue en `NULL` y `external_publication_error` queda marcado como `capacity_deferred:*` o se reconoce como tal si el error legacy contiene `MONETIZATION_ERROR`.

### Forzar export manual

Si una pieza falla quality checks pero quieres sacarla igualmente tras revision humana, el camino sigue siendo manual:

```bash
python -m app.pipelines.editorial_quality_checks check --id 42
python -m app.pipelines.typefully_export dry-run --id 42
python -m app.pipelines.typefully_export export --id 42
```

### Flujo operativo recomendado

- lunes: `refresh -> readiness -> run-daily -> autoexport` de `match_result` y `standings`
- miercoles: en fase 1 solo piezas seguras; en fase 2 ya pueden entrar `stat_narrative` y `metric_narrative` si pasan checks
- viernes: `refresh -> readiness -> run-daily -> autoexport` de `preview`
- domingo: `refresh -> readiness -> run-daily -> autoexport` de resultados seguros

En todos los casos:

- `stat_narrative`, `metric_narrative` y `viral_story` solo autoexportan si su fase esta activa y pasan `editorial_quality_checks`
- la revision fina, programacion y salida final siguen ocurriendo en Typefully

### Logs y observabilidad

El slot de Windows escribe en `logs\cron_autoexport.log`. Cada corrida deja una linea-resumen legible:

```text
[2026-03-20 11:20:01 +01:00] [INFO] AUTOEXPORT phase=1 scanned=10 eligible=10 exported=5 blocked=0 capacity_deferred=5 failed=0
```

El ultimo resumen estructurado se persiste ademas en `logs/typefully_autoexport_status.json`.

## Autoaprobacion operativa y Editorial Release

La capa de release automatizado vive en:

- `app/services/editorial_approval_policy.py`
- `app/pipelines/editorial_approval.py`
- `app/services/editorial_release_pipeline.py`
- `app/pipelines/editorial_release.py`
- `scripts/windows/editorial_release.ps1`

No sustituye la revision humana. Abre un carril seguro para que las piezas mas mecanicas y menos sensibles lleguen solas a Typefully.

### Politica exacta de autoaprobacion

Autoaprobables:

- `match_result`
- `standings`
- `preview`
- `ranking`

Revision manual obligatoria:

- `stat_narrative`
- `metric_narrative`
- `viral_story`

Bloqueos adicionales de autoaprobacion:

- `text_draft` vacio
- estado distinto de `draft`
- draft ya revisado
- errores de calidad detectados por `editorial_quality_checks`

### Flujo automatizado

```text
draft
-> editorial_approval_policy
-> editorial_quality_checks
-> approved
-> publication_dispatch
-> published
-> typefully_autoexport
-> Typefully draft
```

La autoaprobacion persiste:

- `autoapproved`
- `autoapproved_at`
- `autoapproval_reason`

### CLI operativa

```bash
python -m app.pipelines.editorial_approval status
python -m app.pipelines.editorial_approval dry-run
python -m app.pipelines.editorial_approval dry-run --date 2026-03-16
python -m app.pipelines.editorial_release dry-run
python -m app.pipelines.editorial_release dry-run --date 2026-03-16
python -m app.pipelines.editorial_release run
python -m app.pipelines.editorial_release run --date 2026-03-16
```

### Ejemplo de dry-run

```text
dry_run=true
reference_date=2026-03-16
drafts_found=18
autoapprovable_count=15
autoapproved_count=15
manual_review_count=3
dispatched_count=15
autoexport_scanned_count=15
autoexport_eligible_count=15
autoexport_exported_count=15
autoexport_blocked_count=0
autoexport_failed_count=0
```

### Uso operativo

- `Editorial Day` sigue generando `drafts`
- `Editorial Release` autoaprueba solo piezas seguras
- las narrativas sensibles siguen en `editorial_queue`
- Typefully pasa a ser el panel real para revisar, editar, programar o descartar las piezas seguras ya exportadas
- `typefully_export` manual sigue disponible para cualquier pieza fuera del carril automatico

### Verificar configuracion

`verify-config` valida:

- presencia de `TYPEFULLY_API_KEY`
- presencia de `TYPEFULLY_API_URL`
- estrategia de seleccion del `social_set`

No imprime secretos. Solo informa si la configuracion minima local esta lista.

### Dry-run y validacion local

El dry-run:

- valida elegibilidad del `content_candidate`
- valida que `text_draft` no este vacio
- no hace llamada real a Typefully
- no persiste `external_publication_ref`

Eso permite probar el flujo local aunque no haya acceso real a la API externa en el entorno.

### Trazabilidad persistida en BD

Tras una exportacion correcta a Typefully se guardan:

- `external_publication_ref`: id del draft devuelto por Typefully
- `external_channel`: `typefully`
- `external_exported_at`: momento local del exito de exportacion
- `external_publication_attempted_at`: ultimo intento de salida
- `external_publication_error`: `NULL` en exito

Si falla la exportacion:

- `external_publication_ref` sigue `NULL`
- `external_channel` sigue `NULL`
- `external_exported_at` sigue `NULL`
- `external_publication_attempted_at` guarda el intento
- `external_publication_error` guarda el error del canal

### Diferencia frente a publicar en X

- `x_publish` intenta publicar directamente en X
- `typefully_export` solo crea drafts para revision posterior
- `typefully_export` puede usar `rewritten_text` si existe, pero sin modificar nunca `text_draft`
- Typefully no reemplaza `content_candidates`, la cola editorial ni el dispatcher
- la pieza sigue considerandose resuelta editorialmente en el core antes de llegar al canal externo

### Validacion real local

En este entorno la integracion queda preparada para:

- `verify-config` funcional
- `dry-run` funcional
- cliente HTTP encapsulado
- tests con mocks sin llamadas reales

Para una validacion real local hace falta:

- `TYPEFULLY_API_KEY` valida
- `TYPEFULLY_API_URL` valida
- al menos un `social_set` utilizable en la cuenta
- ejecutar `python -m app.pipelines.typefully_export export --id <ID>` o `export-ready`

### Limitaciones abiertas de Typefully

- el modelo actual soporta una sola referencia externa por `content_candidate`
- no se sincroniza el estado posterior del draft dentro de Typefully
- no se recupera aun URL de share, programacion final ni estado de publicacion del draft
- si hay varios `social_sets`, hoy se necesita fijar uno por config para evitar ambiguedad
- la publicacion real sigue ocurriendo fuera del sistema, dentro de Typefully

## Testing

```bash
pytest
```

## Automatizacion Windows

Windows es el entorno principal actual de operacion. La automatizacion recomendada hoy usa PowerShell y Task Scheduler.

Guia principal:

- `docs/windows_scheduler_setup.md`

Principios:

- PowerShell ejecuta scripts ligeros en `scripts/windows/`
- esos scripts solo invocan `app.pipelines.*`
- no hay WSL obligatorio
- no hay scheduler dentro del backend
- la generacion diaria y la autoexportacion controlada pueden programarse por Task Scheduler
- review queue, `approve/reject`, `dispatch` sensible y la edicion final en Typefully siguen siendo manuales
- `run_editorial_day.ps1` soporta `-PreviewOnly` y `PREVIEW_ONLY=true`
- `typefully_autoexport.ps1` ejecuta internamente `quality_checks -> autoexport`

## Automatizacion con cron

Linux cron queda como opcion futura de despliegue. La referencia se documenta en `docs/cron_setup.md`.

Principios:

- `cron` solo ejecuta scripts shell ligeros
- los scripts shell solo llaman a `app.pipelines.*`
- no hay autopublicacion
- review queue, `approve/reject`, `dispatch` y Typefully siguen siendo manuales
- para primer despliegue puede usarse `PREVIEW_ONLY=true` en `run_editorial_day.sh`

### Cobertura minima incluida

- normalizacion de nombres de equipos
- normalizacion de estados
- parseo de fechas en formato numerico y textual en castellano
- parseo de calendario Futbolme realista
- parseo de clasificacion Futbolme realista
- servicios de consulta sobre competicion
- RSS y FFIB
- servicios de consulta sobre noticias
- enriquecimiento editorial de noticias y consultas derivadas
- resumen editorial estructurado por competicion
- deduplicacion e idempotencia de ingesta

## Configuracion central

Archivos clave:

- `app/config/sources.json`
- `app/config/competitions.json`
- `app/config/team_aliases.json`

Cuando cambie una fuente:

- selectores: `app/scrapers/<fuente>/selectors.py`
- parser: `app/scrapers/<fuente>/parser.py`
- rutas e IDs: `app/config/competitions.json`
- estado tecnico/editorial de competicion: `app/config/competitions.json`

## Riesgos en produccion

- Validar periodicamente que Futbolme siga devolviendo `#latabla` y `.cajaPartido`.
- Mantener throttling moderado y `User-Agent` configurable.
- Guardar HTML fallido cuando haya drift de selectores.
- No asumir que un nombre historico de competicion sigue correspondiendo a la misma ruta una temporada despues.
- Revalidar periodicamente los endpoints RSS publicos de prensa local, porque los paths historicos cambian aunque la fuente siga ofreciendo feed.
