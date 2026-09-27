from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app import services
from app.db import get_session
from app.templating import templates

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/")
def index() -> RedirectResponse:
    return RedirectResponse(f"/month/{date.today():%Y-%m}")


@router.get("/month/{month}", response_class=HTMLResponse)
def month_page(
    request: Request,
    month: Annotated[str, Path(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")],
    session: SessionDep,
):
    try:
        first = date(int(month[:4]), int(month[5:]), 1)
    except ValueError:
        raise HTTPException(404, "Invalid month") from None
    habits, days = services.get_month(session, first.year, first.month)
    return templates.TemplateResponse(
        request,
        "month.html",
        {
            "first": first,
            "today": date.today(),
            "prev_month": (first - timedelta(days=1)).replace(day=1),
            "next_month": days[-1].day + timedelta(days=1),
            "habits": habits,
            "groups": services.month_by_category(session, habits, days),
            "note_blocks": services.note_blocks(session),
            "progress": services.progress([i for d in days for i in d.items]),
        },
    )


@router.get("/day/{day}", response_class=HTMLResponse)
def day_page(request: Request, day: date, session: SessionDep):
    items = services.get_day(session, day)
    return templates.TemplateResponse(
        request,
        "day.html",
        {
            "day": day,
            "today": date.today(),
            "prev_day": day - timedelta(days=1),
            "next_day": day + timedelta(days=1),
            "items": items,
            "groups": services.day_by_category(session, items),
            "note_blocks": services.note_blocks(session),
            "progress": services.progress(items),
        },
    )


@router.get("/habits", response_class=HTMLResponse)
def habits_page(request: Request, session: SessionDep):
    return templates.TemplateResponse(
        request,
        "habits.html",
        {
            "groups": services.habits_by_category(session),
            "categories": services.list_categories(session),
        },
    )
