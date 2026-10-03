from datetime import date, timedelta
from typing import Annotated, Literal

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
    groups = services.month_by_category(session, user, habits, days)
    lead = services.lead_in(session, user, first, habits)
    return templates.TemplateResponse(
        request,
        "month.html",
        {
            "first": first,
            "today": date.today(),
            "prev_month": (first - timedelta(days=1)).replace(day=1),
            "next_month": days[-1].day + timedelta(days=1),
            "habits": habits,
            "groups": groups,
            # Per category: the 6 days before the month, per habit (for the trend's average).
            "lead_in": {g.category.id: {h.id: lead[h.id] for h in g.habits} for g in groups},
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


@router.get("/year/{year}", response_class=HTMLResponse)
def year_page(
    request: Request,
    year: Annotated[int, Path(ge=2000, le=2100)],
    session: SessionDep,
    user: UserDep,
    category: int | None = None,
    focus: bool | None = None,
    view: Literal["all"] | None = None,
):
    """Opens on Focus when some habits are picked for it, else on All (explicit: ?view=all)."""
    categories = services.list_categories(session, user)
    if category is not None and category not in {c.id for c in categories}:
        raise HTTPException(404, "Category not found")
    all_habits = services.list_habits(session, user, active_only=True)
    if category is not None or view == "all":
        focus = False
    elif focus is None:
        focus = any(h.focus for h in all_habits)
    if focus:
        category = None
    stats = services.year_stats(session, user, year, date.today(), category, focus)
    # Computer: weeks as columns (Monday on top), like a contribution graph. Phone: mini months.
    lead = stats.days[0].day.weekday()
    cells = [None] * lead + stats.days
    weeks = [cells[i : i + 7] for i in range(0, len(cells), 7)]
    # Month numbers; the template names them in the page's language.
    month_labels = [
        (w + 1, d.day.month)
        for w, week in enumerate(weeks)
        for d in week
        if d is not None and d.day.day == 1
    ]
    months = [
        (m, [None] * date(year, m, 1).weekday() + [d for d in stats.days if d.day.month == m])
        for m in range(1, 13)
    ]
    return templates.TemplateResponse(
        request,
        "year.html",
        {
            "year": year,
            "today": date.today(),
            # Down to a month: this one in the current year, else the year's last/first month.
            "month_link": (
                date.today().replace(day=1)
                if year == date.today().year
                else date(year, 12 if year < date.today().year else 1, 1)
            ),
            "stats": stats,
            "cells": cells,
            "month_labels": month_labels,
            "months": months,
            "categories": categories,
            "category_names": {c.id: c.name for c in categories},
            "category": category,
            "focus": focus,
            "all_habits": all_habits,
        },
    )
