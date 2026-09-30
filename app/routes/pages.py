from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app import auth, services
from app.db import get_session
from app.templating import templates

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[int, Depends(auth.require_user)]


@router.get("/")
def index() -> RedirectResponse:
    return RedirectResponse(f"/month/{date.today():%Y-%m}")


@router.get("/today")
def today_page() -> RedirectResponse:
    """Stable address for today's checklist (the home-screen app starts here)."""
    return RedirectResponse(f"/day/{date.today()}")


@router.get("/year")
def this_year() -> RedirectResponse:
    return RedirectResponse(f"/year/{date.today().year}")


@router.get("/month/{month}", response_class=HTMLResponse)
def month_page(
    request: Request,
    month: Annotated[str, Path(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")],
    session: SessionDep,
    user: UserDep,
):
    try:
        first = date(int(month[:4]), int(month[5:]), 1)
    except ValueError:
        raise HTTPException(404, "Invalid month") from None
    habits, days = services.get_month(session, user, first.year, first.month)
    return templates.TemplateResponse(
        request,
        "month.html",
        {
            "first": first,
            "today": date.today(),
            "prev_month": (first - timedelta(days=1)).replace(day=1),
            "next_month": days[-1].day + timedelta(days=1),
            "habits": habits,
            "groups": services.month_by_category(session, user, habits, days),
            "streaks": services.streaks(session, user, date.today()),
            "note_blocks": services.note_blocks(session, user),
            "progress": services.progress([i for d in days for i in d.items]),
        },
    )


@router.get("/day/{day}", response_class=HTMLResponse)
def day_page(request: Request, day: date, session: SessionDep, user: UserDep):
    items = services.get_day(session, user, day)
    return templates.TemplateResponse(
        request,
        "day.html",
        {
            "day": day,
            "today": date.today(),
            "prev_day": day - timedelta(days=1),
            "next_day": day + timedelta(days=1),
            "items": items,
            "groups": services.day_by_category(session, user, items),
            "streaks": services.streaks(session, user, date.today()),
            "note_blocks": services.note_blocks(session, user),
            "progress": services.progress(items),
        },
    )


@router.get("/habits", response_class=HTMLResponse)
def habits_page(request: Request, session: SessionDep, user: UserDep):
    return templates.TemplateResponse(
        request,
        "habits.html",
        {
            "groups": services.habits_by_category(session, user),
            "categories": services.list_categories(session, user),
        },
    )


MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@router.get("/year/{year}", response_class=HTMLResponse)
def year_page(
    request: Request,
    year: Annotated[int, Path(ge=2000, le=2100)],
    session: SessionDep,
    user: UserDep,
    category: int | None = None,
):
    categories = services.list_categories(session, user)
    if category is not None and category not in {c.id for c in categories}:
        raise HTTPException(404, "Category not found")
    stats = services.year_stats(session, user, year, date.today(), category)
    # Computer: weeks as columns (Monday on top), like a contribution graph. Phone: mini months.
    lead = stats.days[0].day.weekday()
    cells = [None] * lead + stats.days
    weeks = [cells[i : i + 7] for i in range(0, len(cells), 7)]
    month_labels = [
        (w + 1, MONTH_NAMES[d.day.month - 1])
        for w, week in enumerate(weeks)
        for d in week
        if d is not None and d.day.day == 1
    ]
    months = [
        (
            name,
            [None] * date(year, m + 1, 1).weekday()
            + [d for d in stats.days if d.day.month == m + 1],
        )
        for m, name in enumerate(MONTH_NAMES)
    ]
    return templates.TemplateResponse(
        request,
        "year.html",
        {
            "year": year,
            "today": date.today(),
            "stats": stats,
            "cells": cells,
            "month_labels": month_labels,
            "months": months,
            "categories": categories,
            "category": category,
        },
    )
