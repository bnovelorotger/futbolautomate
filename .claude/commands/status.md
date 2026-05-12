# /status — Estado del pipeline editorial

Muestra un snapshot rápido del estado actual de la cola editorial. Útil para saber qué hay pendiente, qué se ha aprobado y qué se ha publicado hoy (o en los últimos días).

## Instrucciones

Ejecuta los siguientes comandos en orden y presenta los resultados de forma clara:

1. **Cola de hoy**
   ```
   python -m app.pipelines.runner editorial_queue show --date <HOY>
   ```

2. **Candidatas pendientes de aprobación**
   ```
   python -m app.pipelines.runner editorial_approval dry-run --date <HOY>
   ```

3. **Quality checks**
   ```
   python -m app.pipelines.runner editorial_quality_checks dry-run --date <HOY>
   ```

4. **Últimas ejecuciones del scraper** (si hay acceso a la DB)
   - Consulta `scraper_runs` ordenado por `started_at DESC LIMIT 10`
   - O lanza: `python -m app.pipelines.runner system_check editorial-readiness`

## Formato de salida

Presenta un resumen así:
```
📅 Fecha: YYYY-MM-DD
📥 Draft:     N
✅ Approved:  N  
📤 Published: N
❌ Rejected:  N
⚠️  Quality fails: N

Próxima acción: [descripción]
```

Si hay candidatas en draft que podrían aprobarse, indícalo. Si hay fallos de quality checks, muestra qué tipo de error es el más frecuente.
