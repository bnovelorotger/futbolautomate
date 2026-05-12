# /refresh — Refresco de datos desde fuentes externas

Lanza el pipeline de ingesta para todas las competiciones integradas. Equivale a ejecutar `scripts/windows/refresh_data.ps1` pero desde el CLI de Python.

**Argumento opcional:** código de competición específico. Si se proporciona, solo refresca esa competición.

## Instrucciones

Competición objetivo: `$ARGUMENTS` (si está vacío, refresca todas las integradas)

### Caso 1: Competición específica

Si `$ARGUMENTS` no está vacío:
```bash
python -m app.pipelines.runner run_competition --competition <COMPETICION> 
```

Muestra el resumen: fuentes scrapeadas, registros encontrados/insertados/actualizados.

### Caso 2: Todas las competiciones

Si `$ARGUMENTS` está vacío:
```bash
python -m app.pipelines.runner run_daily
```

Este comando itera todas las competiciones con `status = integrated` y también refresca noticias desde FFIB, Diario Mallorca y Última Hora.

Muestra un resumen por competición al finalizar.

### Post-refresh

Después del refresco, sugiere el siguiente paso natural:
- Si hay partidos nuevos → `python -m app.pipelines.runner results_roundup show`
- Si hay cambios en clasificaciones → `python -m app.pipelines.runner standings_history compare`
- Si es lunes → recuerda ejecutar `/release` o el pipeline editorial completo

## Competiciones disponibles
- `tercera_rfef_g11`
- `segunda_rfef_g3_baleares`
- `division_honor_mallorca`
- `tercera_federacion_femenina_g11`
- `primera_rfef_baleares`
- `division_honor_ibiza_form`
- `division_honor_menorca`
