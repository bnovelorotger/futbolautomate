# /approve — Aprobación editorial

Ejecuta el flujo de aprobación editorial para una fecha dada. Por defecto usa la fecha de hoy.

**Argumento opcional:** fecha en formato `YYYY-MM-DD`. Si no se proporciona, usa hoy.

## Instrucciones

Fecha a usar: `$ARGUMENTS` (si está vacío, usa la fecha de hoy en formato YYYY-MM-DD)

### Paso 1: Preview de aprobación (dry-run)

```bash
python -m app.pipelines.runner editorial_approval dry-run --date <FECHA>
```

Muestra el resultado completo. Extrae y resume:
- Cuántas candidatas serían aprobadas automáticamente (`autoapprovable_count`)
- Cuántas requieren revisión manual (`manual_review_count`)
- Motivos de bloqueo más frecuentes (campo `policy_reason`: `quality_errors_present`, `manual_review_policy`, etc.)

### Paso 2: Decisión

- Si `autoapprovable_count == 0`: informa al usuario que no hay candidatas aprobables automáticamente para esa fecha y detente. Indica si hay candidatas bloqueadas por quality checks o por política manual.
- Si `autoapprovable_count > 0`: pregunta al usuario:

  > ¿Quieres aprobar estas N candidatas? Responde sí para continuar.

### Paso 3: Ejecución de la aprobación

Solo si el usuario confirma con "sí":

```bash
python -m app.pipelines.runner editorial_release run --date <FECHA>
```

> Nota: `editorial_approval` no tiene subcomando `run` independiente. La aprobación real se ejecuta a través del pipeline de release, que llama internamente a `autoapprove(dry_run=False)` antes de despachar y exportar.

### Paso 4: Resumen

Muestra el número de candidatas aprobadas y publicadas. Si el resultado es exitoso, sugiere ejecutar `/release` si aún no se ha exportado, o confirma que el export ya se ha generado como parte del paso anterior.

## Restricciones

- Nunca ejecutes el paso 3 sin haber mostrado antes el dry-run del paso 1
- Si hay errores en el paso 3, muestra el mensaje de error completo y sugiere revisar `editorial_quality_checks dry-run` para diagnosticar fallos
- No confundas `editorial_approval dry-run` (solo preview) con la aprobación real (paso 3)
