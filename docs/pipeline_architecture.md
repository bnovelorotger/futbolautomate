# Arquitectura del pipeline editorial — "máquina engrasada"

Documento de referencia operativa para futbolautomate tras la revisión profunda
P0–P2 (mayo 2026). Cubre el flujo completo Scraping → Publicación X, las tareas
del Task Scheduler que lo orquestan, los invariantes que deben cumplirse y el
mapa de tipos de contenido cableados.

## Flujo end-to-end

```
+----------------+    +-------------------+    +---------------------+
|  Refresh data  |    |  Editorial day    |    |  Editorial release  |
| refresh_data   | -> | run_editorial_day | -> | editorial_release   |
|     .ps1       |    |       .ps1        |    |       .ps1          |
+----------------+    +-------------------+    +---------------------+
        |                      |                          |
        v                      v                          v
   scrapers/             editorial_planner       _run_internal:
   ingest_*              run_daily                quality_precheck
                         (DRAFT en DB)            -> autoapprove
                                                  -> dispatch
                                                  -> browser publish
                                                                |
                                                                v
                                                  +-----------------------+
                                                  |  Catch-up T+30min     |
                                                  | auto_publish_browser  |
                                                  |        .ps1           |
                                                  +-----------------------+
```

## Slots de la parrilla (Europe/Madrid)

Fuente: `app/config/publication_schedule.json` + tareas `futbol_release_*` en
`scripts/windows/setup_scheduler.ps1`.

| Día | Refresh | Editorial | Release | Catch-up | Tipos publicables | Límite |
|-----|---------|-----------|---------|----------|-------------------|--------|
| Lun | 06:30 + 14:00 | 07:30 | 09:15 | 09:45 | results_roundup, standings_roundup, race_narrative, milestone_story, top_scorer_update | 4 |
| Mar | 07:00 + 14:00 | 18:30 | 20:00 | 20:30 | ranking, standings_roundup | 3 |
| Mié | 07:00 + 14:00 | 18:30 | 20:00 | 20:30 | viral_story, metric_narrative, stat_narrative | 4 |
| Jue | 07:00 + 14:00 | 18:30 | 20:00 | 20:30 | top_scorer_update, ranking | 3 |
| Vie | 07:00 + 14:00 | 08:00 | 13:00 | 13:30 | featured_match_preview, match_impact_scenario | 4 |
| Sáb | 07:00 + 14:00 | 09:30 | 11:00 | 11:30 | preview | 2 |
| Dom | 06:30 + 14:00 + 20:00 | 20:45 | 21:15 | 21:45 | results_roundup, standings_roundup | 2 |

Tareas auxiliares diarias: `futbol_editorial_day_plan` (08:00, Telegram),
`futbol_summary` (21:00), `futbol_editorial_digest` (22:00, Telegram),
`futbol_engagement` (12:30 L–V), `futbol_backup` (03:00), `futbol_log_cleanup`
(domingo 04:00), `futbol_session_check` (lunes 06:00).

## Ciclo de vida de una candidata

```
              +---- inserción por editorial_planner
              v
           draft  (status=DRAFT, reviewed_at=NULL, quality_check_passed=NULL)
              |
              | quality_checks.check_candidates
              | (setea quality_check_passed/errors/timestamp;
              |  NO toca reviewed_at ni status)
              v
   autoapprove decision:
   - autoapprovable + dry_run=False -> APPROVED (reviewed_at=now, approved_at=now,
                                                  autoapproved=True)
   - !autoapprovable -> sigue DRAFT (manual review)
              |
              v
   publication_dispatcher.dispatch_candidates
   (status=PUBLISHED; published_at=now SI estaba NULL — invariante P1.5a)
              |
              v
   x_browser_publication_service.publish_pending
   (XPublicationScheduler filtra por día/hora/tipo;
    publica en X via Playwright;
    setea external_publication_ref="x-browser:<ts>")
              |
              v
        published + ref  (estado final)
```

## Invariantes

Las siguientes condiciones DEBEN cumplirse. Si fallan, hay bug.

1. **No re-stamping de `published_at`**: `dispatch_candidates` solo asigna
   `published_at = now` si el campo era NULL. Si ya existía, se respeta.
   (`app/services/publication_dispatcher.py:200`)

2. **Telegram bloqueado en tests**: ningún test toca la red real de Telegram.
   La fixture autouse `_block_real_telegram` en `tests/conftest.py` parchea
   `TelegramNotificationService.send_message`/`get_updates`. Tests que necesitan
   el comportamiento real opt-in vía `@pytest.mark.real_telegram`.

3. **Una sola tarea por slot**: no debe haber tareas `uFutbolBalear *` (legacy)
   ni duplicados. `setup_scheduler.ps1` borra cualquier `uFutbolBalear*` al
   correr. Verificar con
   `Get-ScheduledTask | Where-Object { $_.TaskName -like "uFutbolBalear*" }`.

4. **Cache de `_pending_drafts` por instancia**: dentro de un único
   `_run_internal`, las múltiples llamadas (`quality_precheck`, `autoapprove`,
   `status`) comparten el resultado. Se invalida automáticamente al autoaprobar
   filas (porque cambian de estado).
   (`app/services/editorial_approval_policy.py:113-115`)

5. **Anclaje del digest al `reference_date`**: `pipeline_summary_service.summary`
   construye la ventana a partir del `reference_date` recibido, no del reloj.
   Permite re-generar digests históricos sin distorsión.
   (`app/services/pipeline_summary_service.py:106-110`)

6. **Catch-up T+30min tras cada release**: si el release dispatcha pero el
   browser publish falla a mitad, `auto_publish_browser.ps1` recoge las piezas
   con `status=PUBLISHED` + `external_publication_ref=NULL` dentro de la ventana
   de 96 h. Tareas `futbol_publish_catchup_*`.

7. **Rescate de approved huérfanos**: `_run_internal` llama
   `dispatch_service.list_ready()` además del autoaprobado del run, así si una
   pieza quedó como `APPROVED` por crash del run anterior, se dispatcha en el
   siguiente. Se loggea WARNING `editorial_release_rescue` cuando aplica.
   (`app/services/editorial_release_pipeline.py:127-137`)

## Mapa de tipos de contenido

Tipos **cableados E2E** (generan, autoaprueban, publican):

| Tipo | Genera (días) | Autoaprob (días) | Publica (días) |
|------|---------------|------------------|----------------|
| `results_roundup`  | lun, dom | siempre | lun 09:15, dom 21:15 |
| `standings_roundup`| lun, mar, dom | siempre | lun 09:15, mar 20:00, dom 21:15 |
| `ranking`          | mar, jue | mar/mié/jue | mar 20:00, jue 20:00 |
| `top_scorer_update`| lun, jue | lun/jue | lun 09:15, jue 20:00 |
| `preview`          | sab | sab | sab 11:00 |
| `featured_match_preview`| vie | vie | vie 13:00 |
| `match_impact_scenario` | vie | vie | vie 13:00 |
| `metric_narrative` | mié | mar/mié | mié 20:00 |
| `viral_story`      | mié | mar/mié | mié 20:00 |
| `stat_narrative`   | mié | mar/mié | mié 20:00 |
| `milestone_story`  | lun | lun (P1.5) | lun 09:15 |

Tipos **autoaprob condicional** (reglas estrictas):

- `race_narrative` — lunes, evaluado por `_RACE_NARRATIVE_AUTO_RULES`
  (min_priority, max equipos, max points_span, max rounds_remaining).

Tipos **eliminados** del flujo automático (P1.6): `featured_match_event`,
`form_event`, `standings_event`. Los CLI manuales `generate` se eliminaron;
los servicios permanecen como inputs para otros generadores.

Tipos **legacy** (no se generan): `match_result`, `standings`, `form_ranking`.

## Observabilidad

Eventos clave de log estructurado:

- `editorial_pending_drafts` (`editorial_approval_policy.py`): incluye
  `rows_total_sql` (count crudo DB) vs `rows_eligible` (post window filter).
  Comparar ambos distingue "DB no tenía" de "filtro de ventana excluyó".
- `editorial_release_phase` (`editorial_release_pipeline.py`): IDs implicados
  en cada fase (quality_precheck, autoapprove, ready_approved_rescue, dispatch).
- `editorial_release_rescue` (WARNING): se emite cuando `list_ready()` recoge
  candidatas APPROVED del run anterior. Señal de problema upstream.
- `match_impact_scenario_no_candidates` (`editorial_planner.py`): común en
  fin de temporada, no es bug si una competición ya no tiene jornadas.

Comandos de diagnóstico:

- `python -m app.pipelines.runner editorial_day_plan --date YYYY-MM-DD` —
  agenda del día (publicables/manual/bloqueadas).
- `python -m app.pipelines.runner pipeline_summary --date YYYY-MM-DD --days N` —
  bloqueos, publicación, alertas.
- `python -m app.pipelines.runner editorial_daily_digest --date YYYY-MM-DD` —
  digest del día (con métricas rewrite).
- `python -m app.pipelines.x_publish browser-pending --dry-run` — qué
  publicaría el browser si corriera ahora.

## Failure modes conocidos y respuesta

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| `drafts_found` muy bajo en release | Editorial run-daily no commiteado a tiempo, o filtro window excluye | Mirar `editorial_pending_drafts`: si `rows_total_sql` bajo, es commit; si alto, es ventana |
| 0 publicaciones tras release exitoso | Dispatch OK, browser publish falló | Revisar `cron_publish_browser.log` y catch-up T+30min |
| Notificaciones Telegram duplicadas | Tests sin mock disparando red real | Verificar fixture `_block_real_telegram` |
| Pieza vieja re-publicada | Dispatcher re-stampó `published_at` | Verificar `dispatcher` mantiene el invariante P1.5a |
| `match_impact_scenario` produce 0 | Fin de temporada en esa competición | Esperado; ver `match_impact_scenario_no_candidates` log |
| Drafts atrapados con `reference_date` pasada | Window check exige igualdad exacta de fecha | Issue conocido; rescate manual o esperar al mismo día de la semana |
