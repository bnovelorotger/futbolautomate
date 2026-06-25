# futbolautomate

Python automation project for Balearic football coverage, combining scraping, structured persistence, editorial scoring, export pipelines, and browser-assisted publication workflows.

This repository is closer to a product automation system than to a typical scraping script. It collects match, standings, and news data, turns it into editorial candidates, applies deterministic formatting and quality rules, and prepares outputs for publishing workflows.

Detailed internal documentation for the current iteration is available in [docs/README_detailed.md](docs/README_detailed.md).

## What this project demonstrates

- Multi-source sports data ingestion
- SQLAlchemy-based persistence and Alembic migrations
- Structured CLI operations with Typer
- Editorial scoring, approval, and release logic
- Export and publication workflows for social channels
- Strong test coverage across services, pipelines, and scrapers

## Current scope

The current public snapshot reflects the v1.5 generation of the project and includes:

- match, standings, and news ingestion
- standings snapshots and event tracking
- team form and match-importance logic
- editorial candidate generation and approval rules
- base exports and release orchestration
- browser-assisted publication flows for X
- PNG rendering for standings roundup assets

## Repository structure

```text
app/                       Main application code
docs/                      Operational and technical documentation
migrations/                Database migrations
scripts/                   Helper scripts and scheduler utilities
tests/                     Unit and integration tests
pyproject.toml             Project configuration
requirements.txt           Dependencies
.env.example               Environment reference
```

## Stack

- Python
- SQLAlchemy
- Alembic
- Pydantic
- Typer
- Playwright
- pytest

## How to run

Create an environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Configure environment variables:

1. Copy `.env.example` to `.env`
2. Set at least the database and publication credentials you need for your workflow

Apply migrations:

```bash
alembic upgrade head
```

Run representative commands:

```bash
python -m app.pipelines.run_daily
python -m app.pipelines.run_source --source futbolme --competition division_honor_mallorca --target matches
python -m app.pipelines.editorial_release dry-run --date 2026-03-26
python -m app.pipelines.export_base generate --date 2026-03-26
pytest
```

## Recommended review entry points

- `docs/pipeline_architecture.md`
- `docs/README_detailed.md`
- `app/pipelines/run_daily.py`
- `app/services/editorial_content_generator.py`
- `app/services/export_base_service.py`

## Recruiter summary

This is one of the strongest repositories in the portfolio because it shows system design, automation, persistence, workflow orchestration, and product thinking, not just isolated scraping.
