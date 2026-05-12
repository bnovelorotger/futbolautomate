# /review-conventions — Revisión de convenciones de código

Revisa los cambios en la rama actual (o ficheros específicos) y verifica que cumplen las convenciones del proyecto definidas en `CLAUDE.md`. Útil antes de mergear cualquier feature branch.

Compatible con Codex: genera un informe de issues que cualquier agente puede usar para corregir el código.

**Argumento opcional:** ruta de fichero o directorio a revisar. Si está vacío, revisa todos los cambios respecto a `main`.

## Instrucciones

### 1. Determinar el scope

- Si `$ARGUMENTS` contiene una ruta: revisa ese fichero o directorio
- Si está vacío: obtén los ficheros modificados con `git diff --name-only main` y revísalos

### 2. Verificar convenciones (por cada fichero Python)

Comprueba cada uno de estos puntos:

**Arquitectura:**
- [ ] ¿Hay lógica de negocio en `app/pipelines/`? (no debe haberla — solo parsing de CLI y llamadas a servicios)
- [ ] ¿Hay queries SQL directas en `app/services/`? (deben ir en `app/db/repositories/`)
- [ ] ¿Hay `print()` en vez de `logging`?

**Tipado:**
- [ ] ¿Todas las funciones tienen type hints en parámetros y return?
- [ ] ¿Hay `from __future__ import annotations` al inicio del fichero?

**Patrones:**
- [ ] ¿El acceso a la DB usa `session_scope()` + repositorio?
- [ ] ¿Las operaciones con estado aceptan `dry_run: bool = False`?
- [ ] ¿Los errores de dominio usan `app.core.exceptions.*`?

**Comentarios:**
- [ ] ¿Hay comentarios que explican QUÉ hace el código en vez de POR QUÉ? (eliminar)
- [ ] ¿Hay docstrings multi-línea innecesarios?

### 3. Informe

Para cada issue encontrado, reporta:
- Fichero y línea
- Convención violada
- Sugerencia de corrección (una línea)

Si no hay issues: confirma que el código sigue las convenciones.

### 4. Corrección (solo si el usuario lo pide explícitamente)

No corrijas automáticamente. Muestra el informe primero y espera confirmación.
