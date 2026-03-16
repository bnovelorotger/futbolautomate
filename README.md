# futbolautomate

Automatizacion en Python para una cuenta de X/Twitter centrada en futbol balear. El proyecto combina scraping de competiciones y noticias, persistencia en base de datos, generacion de piezas editoriales y flujos de publicacion/exportacion.

La documentacion detallada de esta iteracion se conserva en [docs/README_detailed.md](docs/README_detailed.md).

## Que incluye ahora

- Ingesta de partidos, clasificaciones y noticias desde varias fuentes.
- Catalogo de competiciones y reglas editoriales configurables.
- Persistencia con SQLAlchemy y migraciones con Alembic.
- Pipelines CLI con Typer para scraping, consultas y operativa editorial.
- Flujos para aprobacion editorial, exportacion a Typefully y publicacion en X.
- Suite de tests unitarios e integracion.

## Estructura principal

```text
app/             Codigo fuente principal
docs/            Documentacion y notas operativas
migrations/      Migraciones de base de datos
scripts/         Scripts auxiliares para cron y Windows
tests/           Tests unitarios e integracion
.env.example     Variables de entorno de referencia
pyproject.toml   Dependencias y configuracion del proyecto
```

## Como ejecutar

1. Crear entorno virtual e instalar dependencias:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. Crear `.env` a partir de `.env.example` y ajustar al menos `DATABASE_URL`.

3. Aplicar migraciones:

```bash
alembic upgrade head
```

4. Ejecutar pipelines principales:

```bash
python -m app.pipelines.run_daily
python -m app.pipelines.run_source --source futbolme --competition division_honor_mallorca --target matches
python -m app.pipelines.editorial_ops preview-day --date 2026-03-16
python -m app.pipelines.typefully_export verify-config
python -m app.pipelines.x_auth start-auth
```

5. Ejecutar tests:

```bash
pytest
```

## Estado actual del desarrollo

- La base tecnica de scraping, persistencia y consultas ya existe y tiene tests.
- El repo contiene capa editorial, cola de aprobacion y release hacia Typefully/X a nivel de codigo.
- La operativa real depende de credenciales, base de datos y tareas programadas locales.
- Falta endurecer el flujo de trabajo de equipo: ramas, CI, politicas de revision y despliegue.

## Control de versiones

La rama principal del repositorio es `main`. A partir de este punto, cada cambio debe entrar mediante commits pequenos y ramas de trabajo acotadas.
