# CLAUDE.md — futbolautomate

Automated editorial pipeline for Balearic football (fútbol balear). Scrapes match data, standings, and news from multiple Spanish football sources, persists everything to PostgreSQL, generates editorial content (roundups, previews, narratives), validates and approves it, then exports as structured JSON and optionally publishes to X (Twitter).

---

## Quick start

```bash
# Install dependencies
python -m venv .venv
.venv/Scripts/activate           # Windows
pip install -r requirements.txt

# Apply database migrations
alembic upgrade head

# Verify system health
python -m app.pipelines.runner system_check editorial-readiness

# Run tests
pytest
```

Environment variables live in `.env` (copy from `.env.example`). Minimum required: `DATABASE_URL`.

Docker Compose starts the dev database:
```bash
docker-compose up -d   # starts PostgreSQL on localhost:5432
```

---

## Project layout

```
app/
  channels/     Publishing channels (X/Twitter, Typefully)
  config/       JSON configuration files (competitions, rules, schedules)
  core/         Domain models, enums, settings, exceptions, logging
  db/           SQLAlchemy ORM models + Alembic migrations + repositories
  llm/          LLM clients (OpenAI editorial rewrite)
  normalizers/  Data normalization (dates, match statuses)
  pipelines/    CLI entry points — one file per command group
  presenters/   Output formatters (console, JSON)
  schemas/      Pydantic schemas for scraper output and internal DTOs
  scrapers/     Web scraping modules (futbolme, soccerway, FFIB, news)
  services/     Business logic — main code lives here
  templates/    Jinja2 HTML templates (standings card PNG)
  utils/        Shared utilities (time, hashing, text)

migrations/     Alembic migration versions (timestamped)
scripts/
  windows/      PowerShell scripts for Windows Task Scheduler automation
  cron/         Bash scripts for Linux cron automation
tests/
  unit/         Unit tests per module
  integration/  Full-pipeline integration tests
```

---

## Running the CLI

All commands go through:
```bash
python -m app.pipelines.runner <command> [options]
```

### Data ingestion
```bash
# Scrape one source for one competition
python -m app.pipelines.runner run_source --source futbolme --competition tercera_rfef_g11 --target matches

# Daily refresh (all integrated competitions)
python -m app.pipelines.runner run_daily
```

### Editorial pipeline
```bash
# Generate daily content (previews, roundups)
python -m app.pipelines.runner editorial_ops preview-day --date 2026-05-12

# Full daily editorial pipeline
python -m app.pipelines.runner editorial_ops run-daily

# Quality checks (dry-run)
python -m app.pipelines.runner editorial_quality_checks dry-run --date 2026-05-12

# Approval (dry-run)
python -m app.pipelines.runner editorial_approval dry-run --date 2026-05-12

# Release and export
python -m app.pipelines.runner editorial_release run --date 2026-05-12
python -m app.pipelines.runner editorial_release dry-run --date 2026-05-12
```

### Content generation (individual)
```bash
python -m app.pipelines.runner results_roundup generate --competition tercera_rfef_g11
python -m app.pipelines.runner standings_roundup generate --competition tercera_rfef_g11
python -m app.pipelines.runner standings_events generate --competition tercera_rfef_g11
python -m app.pipelines.runner team_form generate --competition tercera_rfef_g11
python -m app.pipelines.runner match_importance generate --competition tercera_rfef_g11
python -m app.pipelines.runner story_importance rank-pending
```

### Export
```bash
python -m app.pipelines.runner export_base generate --date 2026-05-12
```

### Publishing (browser — default)
```bash
# Capture/renew X session (opens interactive browser for login)
python -m app.pipelines.runner x_browser_auth capture

# Publish all pending candidates via browser (Playwright + Chromium)
python -m app.pipelines.runner editorial_release run --publish-browser

# Diagnose browser session
python scripts/debug_browser_publish.py
```

### Publishing (X API — optional, requires API credentials)
```bash
python -m app.pipelines.runner x_auth start-auth
python -m app.pipelines.runner x_publish --id <candidate_id>
```

---

## Architecture

### Data flow

```
Scraper → ingest_* service → PostgreSQL
                                  ↓
         editorial_content_generator → content_candidates (status=draft)
                                  ↓
         editorial_quality_checks    → quality_check_passed = true/false
                                  ↓
         editorial_approval_policy  → status=approved (auto or manual)
                                  ↓
         editorial_formatter        → formatted_text + viral_formatted_text
                                  ↓
         publication_dispatcher     → status=published
                                  ↓
         export_base_service        → exports/export_base.json + PNG images
```

### Layer responsibilities

| Layer | Responsibility |
|-------|---------------|
| `pipelines/` | CLI parsing only. No business logic. Delegates to services. |
| `services/` | All business logic. Reads from repos, writes back, returns results. |
| `db/repositories/` | Database access. SQL queries via SQLAlchemy. No business logic. |
| `core/` | Domain models, enums, config. No I/O. |
| `scrapers/` | HTTP fetching + HTML parsing. Returns raw records. |
| `normalizers/` | Pure functions. Input → normalized output. No side effects. |

### Session management

All database access uses the `session_scope()` context manager from `app.db.session`. Repositories are instantiated inside the scope and passed down.

```python
from app.db.session import session_scope

with session_scope() as session:
    repo = SomeRepository(session)
    results = repo.find_by_something(...)
```

### Content candidate lifecycle

```
draft → [quality_checks] → approved/rejected → [formatter] → published
```

Status values are in `app.core.enums.ContentCandidateStatus`:
- `draft` — generated, not yet validated
- `approved` — passed quality checks and approval policy
- `rejected` — failed quality checks or manually rejected
- `published` — dispatched and exported

---

## Domain model

### Competitions (7 integrated)

| Code | Name |
|------|------|
| `tercera_rfef_g11` | 3ª RFEF Baleares |
| `segunda_rfef_g3_baleares` | 2ª RFEF Baleares |
| `division_honor_mallorca` | División Honor Mallorca |
| `tercera_federacion_femenina_g11` | 3ª Federación Femenina |
| `primera_rfef_baleares` | 1ª RFEF Baleares |
| `division_honor_ibiza_form` | División Honor Ibiza |
| `division_honor_menorca` | División Honor Menorca |

Competition definitions live in `app/config/competitions.json`. Integration status, sources, and rules are all there.

### Content types

| Type | Description | When generated |
|------|-------------|----------------|
| `results_roundup` | Aggregated match results by competition | Monday |
| `standings_roundup` | Classification table (compact, with PNG) | Monday |
| `preview` | Upcoming match preview | Thursday/Friday |
| `featured_match_preview` | Highlighted match based on importance score | Friday |
| `ranking` | Team form ranking | Thursday |
| `standings_event` | Significant classification change (leader, playoff, relegation) | Monday |
| `form_event` | Team form narrative (best/worst streak) | Monday |
| `stat_narrative` | Statistical narrative | Wednesday |
| `metric_narrative` | Metric-driven narrative | Wednesday |
| `viral_story` | Short-form shareable content | Wednesday |

Legacy types (`match_result`, `standings`, `form_ranking`) are kept for compatibility. Do not generate new content using them.

### Weekly planner schedule

Configured in `app/config/editorial_schedule.json`. Drives `editorial_ops preview-day`.

- **Monday:** `results_roundup` + `standings_roundup` for all 7 competitions
- **Wednesday:** `stat_narrative`, `metric_narrative`, `viral_story` for the 3 main competitions
- **Thursday:** `preview` + `ranking` for the 5 main competitions (window extends to next Sunday)
- **Friday:** `preview` + `featured_match_preview` for 5 main competitions + DH Mallorca

### Editorial approval policy

Configured in `app/config/editorial_rules.json`. Day-of-week sensitive:

- Tue/Wed: auto-approve `stat_narrative`, `metric_narrative`, `viral_story` if quality checks pass
- Other days: requires manual approval for narrative types

---

## Database

### Running migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "describe_what_changed"

# Check current state
alembic current
```

Migration files are in `migrations/versions/`. Name them with date prefix: `YYYYMMDD_description.py`.

### Key tables

| Table | Purpose |
|-------|---------|
| `competitions` | League/tournament metadata |
| `matches` | Match results and scheduled fixtures |
| `standings` | Current league tables |
| `standings_snapshots` | Historical standings by scraper_run |
| `content_candidates` | All generated editorial content |
| `scraper_runs` | Ingestion job tracking |
| `team_socials` | X handles for teams (used in mention enrichment) |
| `channel_user_tokens` | OAuth tokens for X/Typefully |

---

## Configuration files

All in `app/config/`:

| File | Purpose |
|------|---------|
| `competitions.json` | Competition catalog (sources, urls, rules, status) |
| `editorial_schedule.json` | Weekly planner (what to generate on each day) |
| `editorial_rules.json` | Approval policy, quality thresholds |
| `match_importance.json` | Match scoring weights |
| `standings_zones.json` | Playoff/relegation zone definitions |
| `story_importance.json` | Content type priority weights |
| `team_aliases.json` | Team name variations for scraper normalization |
| `team_name_aliases.json` | Editorial naming conventions |
| `sources.json` | Data source definitions |

---

## Testing

```bash
# Run all tests
pytest

# Run with coverage (matches what CI runs)
pytest tests/unit/ --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/integration/test_editorial_ops.py -v

# Run unit tests only
pytest tests/unit/ -v
```

Tests use real PostgreSQL (configured via `DATABASE_URL` in `.env`). Do not mock the database — integration test reliability depends on hitting a real instance.

Test fixtures are in `tests/conftest.py` and `tests/fixtures/`. Shared helpers are in `tests/helpers.py`.

CI uploads a coverage summary to the GitHub Actions job summary for each run.

---

## Code conventions

- **Type hints everywhere.** All functions and methods must be typed. Use `from __future__ import annotations` at top of file.
- **Pydantic for data boundaries.** Any data entering the system (scraper output, API responses) must be validated with Pydantic.
- **No comments for obvious code.** Only comment WHY something is done when it's non-obvious — a hidden constraint, a bug workaround, or a subtle invariant.
- **Repositories for DB access.** All SQL queries go through `app/db/repositories/`. Services call repositories, not SQLAlchemy directly.
- **No business logic in pipelines.** Pipelines parse CLI args and call services. Period.
- **Dry-run support.** Any operation that modifies state must accept `dry_run: bool = False`.
- **Logging:** Use `logging.getLogger(__name__)` at module level. No `print()` statements.
- **Error handling:** Raise `app.core.exceptions.*` for domain errors. Let framework errors propagate unless you have specific recovery logic.

---

## Environment variables

See `.env.example` for the full list. Key ones:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | (required) | PostgreSQL connection string |
| `APP_ENV` | `local` | Environment mode |
| `DRY_RUN` | `false` | Global dry-run toggle |
| `TIMEZONE` | `Europe/Madrid` | Default timezone for scheduling |
| `X_CLIENT_ID` | — | X OAuth client ID |
| `X_CLIENT_SECRET` | — | X OAuth secret |
| `EDITORIAL_REWRITE_API_KEY` | — | OpenAI API key (optional) |
| `ENABLE_TEAM_MENTIONS` | `true` | Insert @mentions in posts |
| `LEGACY_EXPORT_JSON_ENABLED` | `false` | Enable legacy export format |

---

## Windows Task Scheduler automation

Scripts in `scripts/windows/`:

| Script | Purpose | Recommended schedule |
|--------|---------|---------------------|
| `refresh_data.ps1` | Scrape all competitions | Twice daily (morning + afternoon) |
| `run_editorial_day.ps1` | Generate daily content | Once daily (midday) |
| `editorial_release.ps1` | Approve + export + dispatch | Once daily (afternoon) |
| `readiness_check.ps1` | System health check | Before main scripts |

See `docs/windows_scheduler_setup.md` for detailed Task Scheduler configuration.

---

## Common issues

**`alembic upgrade head` fails:** Check `DATABASE_URL` in `.env` and that PostgreSQL is running (`docker-compose up -d`).

**Scraper returns 0 records:** Check the source URL in `competitions.json` is still valid. Sources occasionally change their URL structure.

**Content stuck in `draft`:** Run `editorial_quality_checks dry-run` to see what's failing, then `editorial_approval dry-run` to see if it would be approved.

**PNG export fails:** Playwright Chromium must be installed: `playwright install chromium`.

**X publishing fails:** Run `x_auth start-auth` to refresh OAuth tokens.

---

## What NOT to do

- Do not add business logic to `pipelines/`. It belongs in `services/`.
- Do not query the database directly in services — use repositories.
- Do not generate new content using legacy types (`match_result`, `standings`, `form_ranking`).
- Do not commit `.env` — it contains secrets.
- Do not hardcode competition codes — read them from `app/config/competitions.json` or `CompetitionIntegrationStatus`.
- Do not skip `session_scope()` — always use it for database access to ensure proper transaction management.
