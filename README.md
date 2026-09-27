# Daily Planner

[![CI](https://github.com/iraynovskyy/daily-planner/actions/workflows/ci.yml/badge.svg)](https://github.com/iraynovskyy/daily-planner/actions/workflows/ci.yml)
![Python 3.14](https://img.shields.io/badge/python-3.14-3776ab)
![FastAPI](https://img.shields.io/badge/FastAPI-HTMX-009688)

A daily habit tracker: tick off habits each day, see the whole month as a grid, and follow your
progress on per-category timelines. Server-rendered with FastAPI + Jinja2, made interactive with
HTMX — no frontend build step.

![Month grid, dark theme](docs/screenshots/month-dark.png)

| Day checklist (light) | Day checklist (dark) |
|---|---|
| ![Day, light theme](docs/screenshots/day-light.png) | ![Day, dark theme](docs/screenshots/day-dark.png) |

## Features
- **Categories** (e.g. Base, Career, Good habits), each with its own progress bar, month grid and timeline
- **Multi-check habits** ("3 meals", "2 videos") and **optional** habits that are tracked but don't count towards progress
- **Month grid**: every day at a glance; click any cell to tick it
- **Timelines** with progress rings per category
- **Drag-and-drop** (or keyboard) reordering and per-row highlight colours
- **Notes** in collapsible blocks (tips, ideas, comfort), editable in place and movable between blocks
- **Light / dark theme** switch, remembered per browser

## Tech stack
| Layer | Choice |
|---|---|
| Web | FastAPI, Jinja2 templates, HTMX, Pico CSS |
| Data | SQLModel (SQLAlchemy) on SQLite; Postgres-ready via `DATABASE_URL` |
| Migrations | Alembic |
| Tooling | uv, Ruff, pytest, pre-commit, GitHub Actions, Dependabot |

## Run locally
Requires [uv](https://docs.astral.sh/uv/).
```bash
uv sync                                   # install dependencies
cp .env.example .env                      # optional, defaults work
uv run alembic upgrade head               # create / upgrade the database schema
uv run uvicorn app.main:app --reload      # http://localhost:8000
```
Data lives in `data/planner.db`, so it survives restarts.

A fresh database is filled once from [`seed.example.toml`](seed.example.toml). To start with your
own habits and notes, copy it to `seed.local.toml` (git-ignored) and edit it, or point `SEED_FILE`
at another file.

## Develop
```bash
uv run pre-commit install                 # once: lint + format on every commit
uv run pytest
uv run ruff check . && uv run ruff format .
# after changing app/models.py:
uv run alembic revision --autogenerate -m "describe change" && uv run alembic upgrade head
```
CI runs lint, format check, a migrations-vs-models check and the tests on every push and pull request.

## Project layout
```
app/
  main.py          app factory, static files, routers
  models.py        Category, Habit (recurring template), DailyEntry (progress per habit per day), Note
  services.py      business logic, no web code
  routes/pages.py  full pages: / (month grid), /day/…, /habits
  routes/api.py    form / HTMX endpoints that return HTML fragments
  templates/       Jinja HTML; partials/ are the fragments HTMX swaps in
  static/          CSS and small vanilla-JS modules (reorder, highlight, notes, timeline, rings, theme)
migrations/        Alembic schema history
seed.example.toml  default categories, habits and notes for a fresh database
tests/             pytest: services and routes
```

## Roadmap
- [ ] PostgreSQL + Docker Compose
- [ ] Login (hashed passwords, secure sessions, CSRF)
- [ ] Deploy to a VPS behind Nginx with HTTPS, automated from GitHub Actions
- [ ] Database backups to S3
- [ ] Health check, uptime monitoring and error tracking
- [ ] Public demo instance with sample data
