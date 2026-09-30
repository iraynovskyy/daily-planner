from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app import auth, services
from app.db import get_session
from app.templating import templates

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[int, Depends(auth.require_user)]


@router.post("/entries/{habit_id}/{day}", response_class=HTMLResponse)
def set_entry(
    request: Request,
    habit_id: int,
    day: date,
    count: Annotated[int, Form()],
    session: SessionDep,
    user: UserDep,
    view: Annotated[Literal["day", "month"], Form()] = "day",
    golden: Annotated[bool | None, Form()] = None,
):
    """HTMX endpoint: saves the count (and gold mark) and returns the re-rendered row/cell +
    progress (overall and for the habit's category)."""
    item = services.set_count(session, user, habit_id, day, count, golden)
    if item is None:
        raise HTTPException(404, "Habit not found")
    category_id = item.habit.category_id
    streaks = services.streaks(session, user, date.today(), habit_id)
    if view == "month":
        habits, days = services.get_month(session, user, day.year, day.month)
        group = next(
            g
            for g in services.month_by_category(session, user, habits, days)
            if g.category.id == category_id
        )
        return templates.TemplateResponse(
            request,
            "partials/month_cell.html",
            {
                "item": item,
                "day": day,
                "category_id": category_id,
                "day_progress": group.days[day.day - 1].progress,
                "cat_progress": group.progress,
                "progress": services.progress([i for d in days for i in d.items]),
                "streaks": streaks,
                "oob": True,
            },
        )
    items = services.get_day(session, user, day)
    return templates.TemplateResponse(
        request,
        "partials/habit_row.html",
        {
            "item": item,
            "day": day,
            "cat_progress": services.progress(
                [i for i in items if i.habit.category_id == category_id]
            ),
            "progress": services.progress(items),
            "streaks": streaks,
            "oob": True,
        },
    )


@router.post("/habits")
def create_habit(
    name: Annotated[str, Form(min_length=1, max_length=100)],
    target_count: Annotated[int, Form(ge=1, le=20)],
    session: SessionDep,
    user: UserDep,
    unit: Annotated[str | None, Form(max_length=20)] = None,
    optional: Annotated[bool, Form()] = False,
    category_id: Annotated[int | None, Form()] = None,
):
    if (
        services.create_habit(session, user, name, target_count, unit, optional, category_id)
        is None
    ):
        raise HTTPException(404, "Category not found")
    return RedirectResponse("/habits", status_code=303)


@router.post("/habits/focus")
def set_focus(
    session: SessionDep,
    user: UserDep,
    year: Annotated[int, Form(ge=2000, le=2100)],
    ids: Annotated[list[int] | None, Form()] = None,
):
    """The year page's "Choose habits" form: the checked habits become the Focus set."""
    if not services.set_focus(session, user, ids or []):
        raise HTTPException(400, "Unknown habit")
    return RedirectResponse(f"/year/{year}?focus=1", status_code=303)


@router.post("/habits/reorder", status_code=204)
def reorder_habits(ids: Annotated[list[int], Form()], session: SessionDep, user: UserDep) -> None:
    """Drag-and-drop endpoint: `ids` = the habits of one category in their new order."""
    if not services.reorder_habits(session, user, ids):
        raise HTTPException(400, "Habits must exist and belong to one category")


@router.post("/habits/{habit_id}")
def update_habit(
    habit_id: int,
    name: Annotated[str, Form(min_length=1, max_length=100)],
    target_count: Annotated[int, Form(ge=1, le=20)],
    session: SessionDep,
    user: UserDep,
    unit: Annotated[str | None, Form(max_length=20)] = None,
    optional: Annotated[bool, Form()] = False,
    category_id: Annotated[int | None, Form()] = None,
):
    habit = services.update_habit(
        session, user, habit_id, name, target_count, unit, optional, category_id
    )
    if habit is None:
        raise HTTPException(404, "Habit or category not found")
    return RedirectResponse("/habits", status_code=303)


@router.post("/habits/{habit_id}/highlight", status_code=204)
def set_habit_highlight(
    habit_id: int,
    session: SessionDep,
    user: UserDep,
    color: Annotated[Literal[*services.HIGHLIGHTS, ""], Form()] = "",
) -> None:
    """Colour picker endpoint; an empty colour removes the highlight."""
    if services.set_highlight(session, user, habit_id, color or None) is None:
        raise HTTPException(404, "Habit not found")


@router.post("/habits/{habit_id}/active")
def set_habit_active(
    habit_id: int, active: Annotated[bool, Form()], session: SessionDep, user: UserDep
):
    if services.set_active(session, user, habit_id, active) is None:
        raise HTTPException(404, "Habit not found")
    return RedirectResponse("/habits", status_code=303)


@router.post("/habits/{habit_id}/delete")
def delete_habit(habit_id: int, session: SessionDep, user: UserDep):
    if services.delete_habit(session, user, habit_id) is None:
        raise HTTPException(404, "Habit not found")
    return RedirectResponse("/habits", status_code=303)


@router.post("/categories")
def create_category(
    name: Annotated[str, Form(min_length=1, max_length=50)], session: SessionDep, user: UserDep
):
    services.create_category(session, user, name)
    return RedirectResponse("/habits", status_code=303)


@router.post("/categories/{category_id}")
def rename_category(
    category_id: int,
    name: Annotated[str, Form(min_length=1, max_length=50)],
    session: SessionDep,
    user: UserDep,
):
    if services.rename_category(session, user, category_id, name) is None:
        raise HTTPException(404, "Category not found")
    return RedirectResponse("/habits", status_code=303)


@router.post("/categories/{category_id}/delete")
def delete_category(
    category_id: int,
    session: SessionDep,
    user: UserDep,
    move_to: Annotated[int | None, Form()] = None,
):
    """Removes a category; if it still has habits they (and their history) move to `move_to`."""
    try:
        category = services.delete_category(session, user, category_id, move_to)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    if category is None:
        raise HTTPException(404, "Category not found")
    return RedirectResponse("/habits", status_code=303)


def _notes_block(request: Request, session: Session, user: int, kind: str):
    """Re-rendered note block, kept open since the user is working in it."""
    return templates.TemplateResponse(
        request,
        "partials/notes.html",
        {
            "kind": kind,
            "title": services.NOTE_KINDS[kind],
            "notes": services.list_notes(session, user, kind),
            "open": True,
        },
    )


@router.post("/notes", response_class=HTMLResponse)
def create_note(
    request: Request,
    kind: Annotated[Literal[*services.NOTE_KINDS], Form()],
    text: Annotated[str, Form(min_length=1, max_length=300)],
    session: SessionDep,
    user: UserDep,
):
    services.create_note(session, user, kind, text)
    return _notes_block(request, session, user, kind)


@router.post("/notes/order", response_class=HTMLResponse)
def reorder_notes(
    request: Request,
    session: SessionDep,
    user: UserDep,
    tip: Annotated[list[int] | None, Form()] = None,
    idea: Annotated[list[int] | None, Form()] = None,
    comfort: Annotated[list[int] | None, Form()] = None,
):
    """Drag-and-drop endpoint: new top-to-bottom ids per block; returns both blocks, open."""
    order = {k: v for k, v in {"tip": tip, "idea": idea, "comfort": comfort}.items() if v}
    if not services.reorder_notes(session, user, order):
        raise HTTPException(400, "Unknown or repeated note ids")
    return templates.TemplateResponse(
        request,
        "partials/note_blocks.html",
        {"note_blocks": services.note_blocks(session, user), "open": True},
    )


@router.post("/notes/{note_id}", response_class=HTMLResponse)
def update_note(
    request: Request,
    note_id: int,
    text: Annotated[str, Form(min_length=1, max_length=300)],
    session: SessionDep,
    user: UserDep,
):
    note = services.update_note(session, user, note_id, text)
    if note is None:
        raise HTTPException(404, "Note not found")
    return _notes_block(request, session, user, note.kind)


@router.post("/notes/{note_id}/delete", response_class=HTMLResponse)
def delete_note(request: Request, note_id: int, session: SessionDep, user: UserDep):
    note = services.delete_note(session, user, note_id)
    if note is None:
        raise HTTPException(404, "Note not found")
    return _notes_block(request, session, user, note.kind)
