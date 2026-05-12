# /release — Pipeline de release editorial

Ejecuta el pipeline completo de release para una fecha dada. Por defecto usa la fecha de hoy.

**Argumento opcional:** fecha en formato `YYYY-MM-DD`. Si no se proporciona, usa hoy.

## Instrucciones

Fecha a usar: `$ARGUMENTS` (si está vacío, usa la fecha de hoy en formato YYYY-MM-DD)

### Paso 1: Dry-run de quality checks

```bash
python -m app.pipelines.runner editorial_quality_checks dry-run --date <FECHA>
```

Muestra el resultado. Si hay fallos críticos, detente y explica qué hay que corregir antes de continuar.

### Paso 2: Dry-run de aprobación

```bash
python -m app.pipelines.runner editorial_approval dry-run --date <FECHA>
```

Muestra cuántas candidatas se aprobarían automáticamente y cuántas requieren revisión manual.

### Paso 3: Confirmación

Antes de ejecutar el release real, muestra un resumen de qué se va a publicar y pregunta al usuario si continúa.

### Paso 4: Release real

Solo si el usuario confirma:
```bash
python -m app.pipelines.runner editorial_release run --date <FECHA>
```

### Paso 5: Verificar export

Después del release, verifica que `exports/export_base.json` ha sido actualizado:
```bash
python -m app.pipelines.runner export_base generate --date <FECHA>
```

Muestra el número de items exportados por competición y tipo de contenido.

## Restricciones
- Nunca ejecutes el release real sin mostrar primero el dry-run
- Si el dry-run muestra 0 candidatas, avisa antes de continuar
- Si hay errores en el paso 4, muestra el mensaje de error completo y sugiere qué revisar
