# /metrics — Tendencias del pipeline editorial

Muestra y analiza las métricas históricas del pipeline editorial. Las métricas se registran automáticamente tras cada `editorial_release run`.

**Argumento opcional:** número de días a consultar (por defecto 30). Ejemplo: `/metrics 7` para la última semana.

## Instrucciones

Días a consultar: `$ARGUMENTS` (si está vacío o no es un número, usa 30)

### Paso 1: Obtener datos

```bash
python -m app.pipelines.runner pipeline_metrics show --days <DÍAS>
```

Si no hay filas: explicar que las métricas se registran automáticamente tras cada `editorial_release run` y sugerir ejecutar el pipeline de release al menos una vez.

### Paso 2: Calcular indicadores

Para cada fila disponible, calcular y mostrar:

- **Tasa de aprobación media** = `aprobadas / generadas × 100` (si generadas > 0)
- **Tasa de publicación media** = `publicadas / aprobadas × 100` (si aprobadas > 0)
- **Días con quality_fails > 0**: listarlos
- **Duración media** del pipeline en segundos

### Paso 3: Detectar anomalías

Marcar explícitamente si se detecta alguna de estas situaciones:

| Condición | Alerta |
|-----------|--------|
| `rejected > approved` en algún día | ⚠️ Más piezas rechazadas que aprobadas — revisar reglas de aprobación |
| `duration_s > 120` en algún día | ⚠️ Pipeline tardó más de 2 minutos |
| `quality_fails > 3` en algún día | ⚠️ Muchos fallos de quality checks |
| Tasa de aprobación < 50% | ⚠️ Revisar `app/config/editorial_rules.json` |

### Paso 4: Diagnóstico y siguiente acción

Según lo que se observe:
- **Fallos de quality frecuentes** → "Revisar `app/services/editorial_quality_checks.py`"
- **Tasa de aprobación baja** → "Revisar `app/config/editorial_rules.json` y la política de auto-aprobación"
- **Pipeline lento** → "Revisar si hay scraping o render PNG que esté tardando"
- **Todo en orden** → "Sistema funcionando con normalidad ✓"

Para ver el estado actual de la cola, ejecuta `/status`.
