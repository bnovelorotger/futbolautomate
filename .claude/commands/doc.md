# /doc — Revisión y actualización de documentación

Revisa que `CLAUDE.md` esté actualizado respecto al estado real del código. Detecta servicios, pipelines o configuraciones nuevas que no estén documentadas, y actualiza lo que haga falta.

Este skill es compatible con Codex: los cambios en CLAUDE.md benefician a cualquier agente que trabaje en el proyecto.

## Instrucciones

### 1. Auditar pipelines vs CLAUDE.md

Haz un glob de `app/pipelines/*.py` y compara los comandos que expone cada pipeline con lo que está documentado en la sección "Running the CLI" de `CLAUDE.md`.

Para cada pipeline no documentado, añade el comando correspondiente.

### 2. Auditar servicios grandes

Comprueba si hay ficheros en `app/services/` con más de 500 líneas que no estén mencionados en CLAUDE.md. Si los hay, añade una nota en la sección de arquitectura.

### 3. Auditar configuración

Lee `app/config/` y verifica que todos los ficheros JSON están listados en la tabla "Configuration files" de `CLAUDE.md`. Añade los que falten.

### 4. Auditar variables de entorno

Lee `app/core/config.py` (la clase `Settings`) y verifica que todas las variables relevantes están en la tabla "Environment variables" de `CLAUDE.md`. Añade las que falten; elimina las que ya no existan.

### 5. Auditar convenciones

Lee 2-3 servicios representativos (`app/services/`) y comprueba si las convenciones de código listadas en CLAUDE.md siguen siendo precisas. Ajusta si algo ha cambiado.

### 6. Actualizar sección "Version actual"

Si el README.md indica una versión diferente a la mencionada en CLAUDE.md, sincroniza.

## Restricciones
- Solo modifica `CLAUDE.md` (y opcionalmente `README.md` si hay inconsistencias obvias)
- No refactorices código
- No añadas secciones nuevas salvo que sean genuinamente necesarias para futuros agentes
