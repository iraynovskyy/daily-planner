# Daily Planner

Daily habit checklist — FastAPI + Jinja2 + HTMX, SQLite (Postgres-ready via `DATABASE_URL`).

## Run locally
```bash
uv sync                                   # install deps
cp .env.example .env                      # optional, defaults work
uv run alembic upgrade head               # create/upgrade the DB schema
uv run uvicorn app.main:app --reload      # http://localhost:8000
```
Data lives in `data/planner.db`, so it survives restarts/reboots.

A fresh database is filled once from `seed.example.toml`. To start with your own habits and notes,
copy it to `seed.local.toml` (git-ignored) and edit it, or point `SEED_FILE` at another file.

## Develop
```bash
uv run pytest
uv run ruff check . && uv run ruff format .
# after changing app/models.py:
uv run alembic revision --autogenerate -m "describe change" && uv run alembic upgrade head
```

## Layout
- `app/models.py` — `Habit` (recurring template) and `DailyEntry` (progress per habit per day)
- `app/services.py` — business logic (no web code)
- `app/routes/pages.py` — full pages (`/` → month grid, `/day/…`, `/habits`); `app/routes/api.py` — form/HTMX endpoints
- `app/templates/` — Jinja HTML; `partials/` are fragments HTMX swaps in
- `migrations/` — Alembic schema history
- `seed.example.toml` — default categories, habits and notes for a fresh database

## Before hosting (TODO)
Add login + `user_id` on tables, CSRF, per-user timezone for "today", Dockerfile, Postgres.
