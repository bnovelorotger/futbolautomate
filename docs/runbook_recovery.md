# Runbook: Recuperacion desde cero

## Cuando usar esto

- Maquina nueva o reinstalacion de Windows
- Corrupcion o borrado accidental de la base de datos
- Reconstruccion del entorno tras un fallo grave

---

## Prerequisitos

Instalar antes de empezar:

- **Python 3.11+** — anadir al PATH del sistema
- **PostgreSQL 17** (nativo) o **Docker Desktop** con `docker-compose`
- **Git**
- **Playwright / Chromium** — necesario tanto para publicacion en X como para tarjetas PNG de standings

---

## Paso 1: Clonar e instalar

```bash
git clone <url-del-repositorio> C:\Users\bnove\Documents\futbolbalear
cd C:\Users\bnove\Documents\futbolbalear

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

---

## Paso 2: Restaurar la configuracion

Copiar el archivo de referencia y rellenar los secretos:

```powershell
Copy-Item .env.example .env
notepad .env
```

Variables obligatorias:

- `DATABASE_URL` — URL de conexion PostgreSQL

Variables opcionales pero recomendadas:

- `EDITORIAL_REWRITE_API_KEY` — clave de OpenAI para reescritura editorial
- `X_CLIENT_ID`, `X_CLIENT_SECRET` — solo si se usa la API de X (no necesario para publicacion via navegador)

Formato de `DATABASE_URL` para instalacion local estandar:

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/futbol_balear
```

Si la ruta de Python no esta en el PATH del sistema, crear `.env.windows` con:

```
PYTHON_BIN=C:\Users\bnove\Documents\futbolbalear\.venv\Scripts\python.exe
```

---

## Paso 3: Restaurar la base de datos

### Opcion A: Desde un backup (preferida)

Los backups se guardan en `backups/` con el formato `backup_YYYYMMDD_HHmmss.dump`.

Crear la base de datos si no existe:

```powershell
$env:PGPASSWORD = "postgres"
psql --host=localhost --port=5432 --username=postgres --command="CREATE DATABASE futbol_balear;"
```

Restaurar desde el dump mas reciente:

```powershell
$env:PGPASSWORD = "postgres"
pg_restore `
    --host=localhost --port=5432 --username=postgres `
    --dbname=futbol_balear --no-owner --no-privileges `
    backups\backup_YYYYMMDD_HHmmss.dump
Remove-Item Env:PGPASSWORD
```

Para listar los backups disponibles:

```powershell
Get-ChildItem backups\*.dump | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

Verificar que la restauracion es correcta:

```bash
python -m app.pipelines.runner system_check editorial-readiness
```

### Opcion B: Base de datos vacia (sin backup)

Arrancar PostgreSQL con Docker:

```bash
docker-compose up -d
```

O si PostgreSQL esta instalado de forma nativa, crear la base de datos manualmente (ver psql arriba).

Aplicar migraciones:

```bash
alembic upgrade head
```

Poblar datos iniciales de identidades sociales:

```bash
python scripts/seed_team_socials.py
```

---

## Paso 4: Restaurar la sesion del navegador de X

La publicacion en X funciona via Playwright con Chromium. La sesion se guarda en `.x_browser_state.json` (no incluido en el repositorio — esta en `.gitignore`).

Si tienes una copia del archivo en un lugar seguro, copiarla a la raiz del proyecto:

```powershell
Copy-Item "ruta\segura\.x_browser_state.json" ".x_browser_state.json"
```

Si no tienes copia, iniciar sesion de nuevo:

```powershell
python -m app.pipelines.x_publish browser-auth-capture
```

Abre un navegador interactivo. Inicia sesion en X con la cuenta de la plataforma. La sesion se guarda automaticamente en `.x_browser_state.json`.

Verificar que la sesion funciona:

```bash
python -m app.pipelines.x_publish browser-auth-verify
python scripts/debug_browser_publish.py
```

Abre un navegador visible y publica un tweet de prueba. Si el tweet aparece en la cuenta, la sesion es valida.

---

## Paso 5: Reconfigurar el Programador de tareas de Windows

Ejecutar como Administrador:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\scripts\windows\setup_scheduler.ps1"
```

Verificar que las tareas se crearon:

```powershell
Get-ScheduledTask | Where-Object { $_.TaskName -like "futbol_*" } | Select-Object TaskName, State | Format-Table
```

Deben aparecer las siguientes tareas:

- `futbol_refresh_morning`, `futbol_refresh_midweek`, `futbol_refresh_other`, `futbol_refresh_afternoon`
- `futbol_editorial_day_mon_sun`, `futbol_editorial_day_wed`, `futbol_editorial_day_fri`, `futbol_editorial_day_other`
- `futbol_release_mon_sun`, `futbol_release_wed`, `futbol_release_fri`, `futbol_release_other`
- `futbol_session_check`
- `futbol_engagement`
- `futbol_summary`
- `futbol_backup`

Ver `docs/windows_scheduler_setup.md` para el horario detallado y la logica de secuencia por dia.

Probar manualmente antes de dejar en automatico:

```powershell
# 1. Scraping
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\refresh_data.ps1"

# 2. Verificacion
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\readiness_check.ps1"

# 3. Contenido (modo seguro)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\run_editorial_day.ps1" -PreviewOnly

# 4. Release simulado
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\editorial_release.ps1" -DryRun

# 5. Release real con publicacion en X
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\editorial_release.ps1"
```

---

## Paso 6: Verificar que el sistema esta sano

```bash
python -m app.pipelines.runner system_check editorial-readiness
python -m app.pipelines.runner competition_catalog status --integrated-only
```

Revisar los logs tras la primera ejecucion completa:

```
logs\cron_refresh.log
logs\cron_readiness.log
logs\cron_editorial.log
logs\cron_release.log
```

Verificar que se generan los exports:

```bash
python -m app.pipelines.runner editorial_release dry-run --date <fecha-hoy>
python -m app.pipelines.runner export_base generate --date <fecha-hoy>
```

Comprobar que `exports/export_base.json` se genera correctamente.

---

## Tiempo estimado

- Maquina nueva con backup reciente: **30-45 minutos**
- Maquina nueva sin backup (BD vacia): **45-60 minutos** + tiempo de re-scraping
- Solo reinstalacion del entorno Python: **10-15 minutos**

---

## Fallos habituales y como resolverlos

**1. `pg_restore` falla con "role does not exist"**
Anadir `--no-owner --no-privileges` al comando (ya incluido en el ejemplo). Si sigue fallando, crear el rol: `psql -c "CREATE ROLE postgres SUPERUSER LOGIN PASSWORD 'postgres';"`.

**2. `alembic upgrade head` falla con "can't connect to server"**
La base de datos no esta corriendo. Comprobar con `docker-compose ps` (Docker) o desde Servicios de Windows (instalacion nativa). Verificar que `DATABASE_URL` en `.env` apunta al host y puerto correctos.

**3. El publisher de X no publica (no navega fuera de /compose/post)**
La sesion ha expirado o el archivo `.x_browser_state.json` no existe. Ejecutar:
```bash
python -m app.pipelines.x_publish browser-auth-capture
```
Luego verificar con `python -m app.pipelines.x_publish browser-auth-verify` y `python scripts/debug_browser_publish.py`.

**4. Los scripts PowerShell no se ejecutan ("no se puede cargar el archivo")**
El sistema bloquea scripts sin firmar. Ejecutar con `-ExecutionPolicy Bypass`. Para evitarlo permanentemente en el usuario actual: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

**5. `system_check editorial-readiness` reporta competiciones sin datos**
La BD esta vacia o el scraping no ha corrido. Ejecutar manualmente `refresh_data.ps1` y esperar. Si la fuente de datos esta caida, ver `app/scrapers/`.

**6. `playwright install chromium` falla por red o proxy**
Intentar con proxy configurado o instalar manualmente desde https://playwright.dev. El navegador es necesario tanto para publicacion en X como para render de tarjetas PNG de standings.

**7. Tareas del scheduler no corren con la pantalla bloqueada**
Normal si la sesion de Windows esta cerrada. Las tareas usan `-LogonType Interactive`: requieren sesion abierta, pero no hace falta ver la pantalla. La pantalla bloqueada (no cerrar sesion) funciona correctamente.
