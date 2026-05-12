# /start — Project startup & readiness check

Verifica que el entorno está listo para trabajar y muestra el estado actual del sistema. Ejecuta esto al inicio de cualquier sesión de trabajo en futbolautomate.

## Instrucciones

1. **Verificar entorno Python**
   - Confirma que `.venv` existe en la raíz del proyecto
   - Confirma que `python -m app.pipelines.runner --help` responde (si el entorno está activado)

2. **Verificar base de datos**
   - Lanza: `python -m app.pipelines.runner system_check editorial-readiness`
   - Si falla con error de conexión, recuerda al usuario: `docker-compose up -d` para levantar PostgreSQL

3. **Mostrar estado del pipeline editorial**
   - Lanza: `python -m app.pipelines.runner editorial_queue show --date $(date +%Y-%m-%d)` (o la fecha actual en formato YYYY-MM-DD)
   - Muestra cuántas candidatas hay en cada estado: draft / approved / published / rejected

4. **Mostrar última ejecución de scraper**
   - Lanza: `python -m app.pipelines.runner system_check editorial-readiness` (ya lo incluye)

5. **Resumen final**
   - Indica si el sistema está listo (✓) o qué falta (qué comando ejecutar)
   - Sugiere el próximo paso natural según el día de la semana y el estado de la cola

## Contexto importante
- La DB es PostgreSQL. En desarrollo corre via Docker Compose.
- El CLI principal es: `python -m app.pipelines.runner <comando>`
- En producción, los scripts de PowerShell en `scripts/windows/` son los que usa el Task Scheduler
