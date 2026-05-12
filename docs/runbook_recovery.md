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
- **Playwright / Chromium** — solo si se generan tarjetas PNG de standings (paso 4)

---

## Paso 1: Clonar e instalar

```bash
git clone <url-del-repositorio> C:\Users\bnove\Documents\futbolbalear
cd C:\Users\bnove\Documents\futbolbalear

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## Paso 2: Restaurar la configuracion

Copiar el archivo de referencia y rellenar los secretos:

```powershell
Copy-Item .env.example .env
notepad .env
```

Variables obligatorias:

- `DATABASE_URL` — URL de conexion (ver formato abajo)
- `X_CLIENT_ID`, `X_CLIENT_SECRET`, `X_BEARER_TOKEN` — credenciales de la app en [developer.x.com](https://developer.x.com)

Formato de `DATABASE_URL` para instalacion local estandar:

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/futbol_balear
```

El resto de variables del `.env.example` tienen valores por defecto funcionales. Si la ruta de Python no esta en el PATH del sistema, crear `.env.windows` con:

```
PYTHON_BIN=C:\Users\bnove\Documents\futbolbalear\.venv\Scripts\python.exe
```

---

## Paso 3: Restaurar la base de datos

### Opcion A: Desde un backup (preferida)

Los backups se guardan en `backups/` con el formato `backup_YYYYMMDD_HHmmss.dump` (formato custom de `pg_dump`).

Primero crear la base de datos si no existe:

```powershell
$env:PGPASSWORD = "postgres"
psql --host=localhost --port=5432 --username=postgres --command="CREATE DATABASE futbol_balear;"
```

Restaurar desde el dump mas reciente:

```powershell
$env:PGPASSWORD = "postgres"
pg_restore `
    --host=localhost `
    --port=5432 `
    --username=postgres `
    --dbname=futbol_balear `
    --no-owner `
    --no-privileges `
    backups\backup_YYYYMMDD_HHmmss.dump
Remove-Item Env:PGPASSWORD
```

Sustituir `backup_YYYYMMDD_HHmmss.dump` por el nombre real del archivo. Para listar los disponibles:

```powershell
Get-ChildItem backups\*.dump | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

Verificar que la restauracion es correcta:

```bash
python -m app.pipelines.system_check editorial-readiness
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

## Paso 4: Reinstalar Playwright

Necesario para generar tarjetas PNG de `standings_roundup`:

```bash
playwright install chromium
```

---

## Paso 5: Reconfigurar el Programador de tareas de Windows

Ver `docs/windows_scheduler_setup.md` para la configuracion completa y detallada.

Verificar que las cuatro tareas existen:

```powershell
Get-ScheduledTask | Where-Object { $_.TaskName -like "uFutbolBalear*" } | Select-Object TaskName, State
```

Si no existen, recrearlas desde el Programador de tareas con los parametros de `docs/windows_scheduler_setup.md`. Las cuatro tareas son:

- `uFutbolBalear Refresh`
- `uFutbolBalear Readiness`
- `uFutbolBalear Editorial Day`
- `uFutbolBalear Editorial Release`

Probar manualmente antes de activar las tareas programadas:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\refresh_data.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\readiness_check.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\run_editorial_day.ps1" -PreviewOnly
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\editorial_release.ps1" -DryRun
```

---

## Paso 6: Verificar que el sistema esta sano

```bash
python -m app.pipelines.system_check editorial-readiness
python -m app.pipelines.competition_catalog status --integrated-only
```

Revisar los logs tras la primera ejecucion completa:

```
logs\cron_refresh.log
logs\cron_readiness.log
logs\cron_editorial.log
logs\cron_release.log
```

Generar un snapshot de prueba:

```bash
python -m app.pipelines.editorial_release dry-run --date <fecha-hoy>
python -m app.pipelines.export_base generate --date <fecha-hoy>
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
Anadir `--no-owner --no-privileges` al comando (ya incluido en el ejemplo de arriba). Si sigue fallando, crear el rol manualmente: `psql -c "CREATE ROLE postgres SUPERUSER LOGIN PASSWORD 'postgres';"`.

**2. `alembic upgrade head` falla con "can't connect to server"**
La base de datos no esta corriendo. Comprobar con `docker-compose ps` (Docker) o desde Servicios de Windows (instalacion nativa). Verificar que `DATABASE_URL` en `.env` apunta al host y puerto correctos.

**3. `playwright install chromium` falla por red corporativa o proxy**
El render de PNG es opcional: si falla, `export_base.json` sigue generandose y `image_path` queda en `null`. Se puede omitir este paso si no se necesitan las tarjetas visuales.

**4. Los scripts PowerShell no se ejecutan ("no se puede cargar el archivo")**
El sistema bloquea scripts sin firmar. Ejecutar con: `powershell.exe -ExecutionPolicy Bypass -File ".\scripts\windows\refresh_data.ps1"`. Para evitarlo permanentemente en el usuario actual: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

**5. `system_check editorial-readiness` reporta competiciones sin datos**
La BD esta vacia o el scraping no ha corrido aun. Ejecutar manualmente `refresh_data.ps1` y esperar a que termine. Si la fuente de datos esta caida, ver documentacion de cada scraper en `app/scrapers/`.
