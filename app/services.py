import calendar
import tomllib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlmodel import Session, SQLModel, col, select

from app.config import settings
from app.models import Category, DailyEntry, Habit, Note

# Row highlight colours a habit can be tinted with (CSS: [data-hl="<name>"]).
HIGHLIGHTS = ("blue", "green", "amber", "rose", "violet")

# Collapsible note blocks shown under the checklist, in this order.
NOTE_KINDS = {"tip": "Own Tips (to Grow)", "idea": "Ideas (to Grow)", "comfort": "Comfort (Life)"}


@dataclass
class DayItem:
    habit: Habit
    entry: DailyEntry

    @property
    def done(self) -> bool:
        return self.entry.count_done >= self.habit.target_count

    @property
    def golden(self) -> bool:
        return self.done and self.entry.golden


@dataclass
class MonthDay:
    day: date
    items: list[DayItem]

    @property
    def progress(self) -> int:
        return progress(self.items)


@dataclass
class CategoryDay:
    category: Category
    items: list[DayItem]

    @property
    def progress(self) -> int:
        return progress(self.items)


@dataclass
class Streak:
    current: int
    best: int


@dataclass
class CategoryMonth:
    category: Category
    habits: list[Habit]
    days: list[MonthDay]

    @property
    def progress(self) -> int:
        return progress([i for d in self.days for i in d.items])


def seed_user(session: Session, user_id: int, seed_file: Path | None = None) -> None:
    """Gives a user without habits the categories, habits and notes from the seed TOML file."""
    if session.exec(select(Habit).where(Habit.user_id == user_id)).first() is not None:
        return
    with open(seed_file or settings.seed_path, "rb") as f:
        seed = tomllib.load(f)
    existing = {c.name: c for c in list_categories(session, user_id)}
    order = 0
    for cat_order, cat in enumerate(seed.get("category", [])):
        category = existing.get(cat["name"]) or Category(
            user_id=user_id, name=cat["name"], icon=cat.get("icon"), sort_order=cat_order
        )
        session.add(category)
        session.flush()
        for h in cat.get("habits", []):
            session.add(
                Habit(
                    user_id=user_id,
                    name=h["name"],
                    category_id=category.id,
                    target_count=h.get("target", 1),
                    unit=h.get("unit"),
                    sort_order=order,
                    optional=h.get("optional", False),
                )
            )
            order += 1
    for i, note in enumerate(seed.get("note", [])):
        session.add(Note(user_id=user_id, kind=note["kind"], text=note["text"], sort_order=i))
    session.commit()


def _owned[T: SQLModel](session: Session, model: type[T], obj_id: int, user_id: int) -> T | None:
    """The row with this id if it belongs to `user_id`; None otherwise (as if it didn't exist)."""
    obj = session.get(model, obj_id)
    return obj if obj is not None and obj.user_id == user_id else None


def list_categories(session: Session, user_id: int) -> list[Category]:
    stmt = (
        select(Category)
        .where(Category.user_id == user_id)
        .order_by(col(Category.sort_order), col(Category.id))
    )
    return list(session.exec(stmt))


def list_habits(session: Session, user_id: int, *, active_only: bool = False) -> list[Habit]:
    """Grouped by category; inside a category required habits come first, then optional ones."""
    stmt = (
        select(Habit)
        .join(Category)
        .where(Habit.user_id == user_id)
        .order_by(
            col(Category.sort_order),
            col(Category.id),
            col(Habit.optional),
            col(Habit.sort_order),
            col(Habit.id),
        )
    )
    if active_only:
        stmt = stmt.where(Habit.active)
    return list(session.exec(stmt))


def habits_by_category(session: Session, user_id: int) -> list[tuple[Category, list[Habit]]]:
    """Every category (even empty ones) with all its habits, for the settings page."""
    habits = list_habits(session, user_id)
    return [
        (c, [h for h in habits if h.category_id == c.id]) for c in list_categories(session, user_id)
    ]


def day_by_category(session: Session, user_id: int, items: list[DayItem]) -> list[CategoryDay]:
    groups = [
        CategoryDay(c, [i for i in items if i.habit.category_id == c.id])
        for c in list_categories(session, user_id)
    ]
    return [g for g in groups if g.items]


def month_by_category(
    session: Session, user_id: int, habits: list[Habit], days: list[MonthDay]
) -> list[CategoryMonth]:
    """Splits a get_month() grid into one grid per category (same day list, fewer rows)."""
    groups = []
    for c in list_categories(session, user_id):
        idx = [k for k, h in enumerate(habits) if h.category_id == c.id]
        if idx:
            groups.append(
                CategoryMonth(
                    c,
                    [habits[k] for k in idx],
                    [MonthDay(d.day, [d.items[k] for k in idx]) for d in days],
                )
            )
    return groups


def _entries(session: Session, user_id: int, first: date, last: date) -> list[DailyEntry]:
    """The user's stored entries from `first` to `last` (inclusive)."""
    stmt = (
        select(DailyEntry)
        .join(Habit, col(Habit.id) == col(DailyEntry.habit_id))
        .where(Habit.user_id == user_id, DailyEntry.date >= first, DailyEntry.date <= last)
    )
    return list(session.exec(stmt))


def _get_or_create_entry(session: Session, habit_id: int, day: date) -> DailyEntry:
    entry = session.exec(
        select(DailyEntry).where(DailyEntry.habit_id == habit_id, DailyEntry.date == day)
    ).first()
    if entry is None:
        entry = DailyEntry(habit_id=habit_id, date=day)
        session.add(entry)
    return entry


def get_day(session: Session, user_id: int, day: date) -> list[DayItem]:
    """Checklist for a day: active habits plus any inactive ones that already have history."""
    entries = {e.habit_id: e for e in _entries(session, user_id, day, day)}
    items = []
    for habit in list_habits(session, user_id):
        entry = entries.get(habit.id)
        if entry is None:
            if not habit.active:
                continue
            entry = DailyEntry(habit_id=habit.id, date=day)
            session.add(entry)
        items.append(DayItem(habit, entry))
    session.commit()
    return items


def get_month(
    session: Session, user_id: int, year: int, month: int
) -> tuple[list[Habit], list[MonthDay]]:
    """Checklist grid for a month: active habits plus inactive ones with progress in that month.

    Read-only: days without a stored entry get unsaved placeholders (count 0).
    """
    first = date(year, month, 1)
    last = first.replace(day=calendar.monthrange(year, month)[1])
    entries = _entries(session, user_id, first, last)
    by_key = {(e.habit_id, e.date): e for e in entries}
    with_history = {e.habit_id for e in entries if e.count_done > 0}
    habits = [h for h in list_habits(session, user_id) if h.active or h.id in with_history]
    days = [
        MonthDay(
            d,
            [
                DayItem(h, by_key.get((h.id, d)) or DailyEntry(habit_id=h.id, date=d))
                for h in habits
            ],
        )
        for d in (first.replace(day=n) for n in range(1, last.day + 1))
    ]
    return habits, days


def set_count(
    session: Session,
    user_id: int,
    habit_id: int,
    day: date,
    count: int,
    golden: bool | None = None,
) -> DayItem | None:
    """Stores the checks for a day. Gold sticks only while the habit is fully done; `golden=None`
    keeps the current mark, so a double-tap's two requests end up gold in either order."""
    habit = _owned(session, Habit, habit_id, user_id)
    if habit is None:
        return None
    entry = _get_or_create_entry(session, habit_id, day)
    entry.count_done = max(0, min(count, habit.target_count))
    if golden is not None:
        entry.golden = golden
    entry.golden = entry.golden and entry.count_done == habit.target_count
    entry.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(entry)
    return DayItem(habit, entry)


def streaks(
    session: Session, user_id: int, today: date, habit_id: int | None = None
) -> dict[int, Streak]:
    """Days in a row each habit was fully done, by habit id (habits never done are missing).

    `current` ends today, or yesterday while today isn't done yet (an unfinished today doesn't
    break it); `best` is the longest run up to today. `habit_id` limits it to one habit.
    """
    stmt = (
        select(DailyEntry.habit_id, DailyEntry.date)
        .join(Habit, col(Habit.id) == col(DailyEntry.habit_id))
        .where(
            Habit.user_id == user_id,
            col(DailyEntry.count_done) >= col(Habit.target_count),
            DailyEntry.date <= today,
        )
        .order_by(col(DailyEntry.habit_id), col(DailyEntry.date))
    )
    if habit_id is not None:
        stmt = stmt.where(DailyEntry.habit_id == habit_id)
    days: dict[int, list[date]] = {}
    for hid, day in session.exec(stmt):
        days.setdefault(hid, []).append(day)
    result = {}
    for hid, dates in days.items():
        run = best = 0
        for prev, day in zip([None, *dates], dates, strict=False):
            run = run + 1 if prev is not None and day - prev == timedelta(days=1) else 1
            best = max(best, run)
        current = run if dates[-1] >= today - timedelta(days=1) else 0
        result[hid] = Streak(current, best)
    return result


def progress(items: list[DayItem]) -> int:
    """Completion % of required habits; optional ones are ignored."""
    items = [i for i in items if not i.habit.optional]
    total = sum(i.habit.target_count for i in items)
    done = sum(min(i.entry.count_done, i.habit.target_count) for i in items)
    return round(100 * done / total) if total else 0


def create_habit(
    session: Session,
    user_id: int,
    name: str,
    target_count: int,
    unit: str | None,
    optional: bool = False,
    category_id: int | None = None,
) -> Habit | None:
    """Adds a habit to `category_id` (default: first category); None if that category is unknown."""
    if category_id is None:
        categories = list_categories(session, user_id)
        if not categories:
            return None
        category_id = categories[0].id
    elif _owned(session, Category, category_id, user_id) is None:
        return None
    last = list_habits(session, user_id)
    habit = Habit(
        user_id=user_id,
        name=name.strip(),
        category_id=category_id,
        target_count=max(1, min(target_count, 20)),
        unit=(unit or "").strip() or None,
        sort_order=max((h.sort_order for h in last), default=-1) + 1,
        optional=optional,
    )
    session.add(habit)
    session.commit()
    session.refresh(habit)
    return habit


def update_habit(
    session: Session,
    user_id: int,
    habit_id: int,
    name: str,
    target_count: int,
    unit: str | None,
    optional: bool = False,
    category_id: int | None = None,
) -> Habit | None:
    habit = _owned(session, Habit, habit_id, user_id)
    if habit is None or (
        category_id is not None and _owned(session, Category, category_id, user_id) is None
    ):
        return None
    if category_id is not None and category_id != habit.category_id:
        # Moving to another category puts the habit at the end of it.
        habit.category_id = category_id
        habit.sort_order = (
            max((h.sort_order for h in list_habits(session, user_id)), default=-1) + 1
        )
    habit.name = name.strip()
    habit.target_count = max(1, min(target_count, 20))
    habit.unit = (unit or "").strip() or None
    habit.optional = optional
    session.commit()
    return habit


def set_active(session: Session, user_id: int, habit_id: int, active: bool) -> Habit | None:
    """Soft delete/restore — history in DailyEntry is always kept."""
    habit = _owned(session, Habit, habit_id, user_id)
    if habit is None:
        return None
    habit.active = active
    session.commit()
    return habit


def delete_habit(session: Session, user_id: int, habit_id: int) -> Habit | None:
    """Removes a habit for good, together with all its history (see set_active to keep it)."""
    habit = _owned(session, Habit, habit_id, user_id)
    if habit is None:
        return None
    for entry in session.exec(select(DailyEntry).where(DailyEntry.habit_id == habit_id)):
        session.delete(entry)
    session.flush()  # entries go before the habit row (FK)
    session.delete(habit)
    session.commit()
    return habit


def reorder_habits(session: Session, user_id: int, habit_ids: list[int]) -> bool:
    """Stores a new order for habits of one category (as dragged in the UI).

    `habit_ids` may be a subset of the category (pages hide inactive habits); the others keep
    their places. Required habits always stay above optional ones. False if the ids are
    unknown, repeated or span several categories.
    """
    habits = list_habits(session, user_id)
    by_id = {h.id: h for h in habits}
    moved = [by_id.get(i) for i in habit_ids]
    if not moved or None in moved or len(set(habit_ids)) != len(habit_ids):
        return False
    if len({h.category_id for h in moved}) != 1:
        return False
    moved.sort(key=lambda h: h.optional)  # stable: keeps the dragged order inside each group
    slots = iter(moved)
    ids = set(habit_ids)
    for i, h in enumerate([next(slots) if h.id in ids else h for h in habits]):
        h.sort_order = i
    session.commit()
    return True


def create_category(session: Session, user_id: int, name: str) -> Category:
    last = list_categories(session, user_id)
    category = Category(
        user_id=user_id, name=name.strip(), sort_order=(last[-1].sort_order + 1) if last else 0
    )
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def delete_category(
    session: Session, user_id: int, category_id: int, move_to: int | None = None
) -> Category | None:
    """Deletes a category; its habits (with their history) move to the end of `move_to`.

    None if either category is unknown. ValueError if it is the last category, or it still has
    habits and `move_to` is missing or the category itself.
    """
    category = _owned(session, Category, category_id, user_id)
    if category is None or (
        move_to is not None and _owned(session, Category, move_to, user_id) is None
    ):
        return None
    if len(list_categories(session, user_id)) == 1:
        raise ValueError("The last category can't be deleted")
    habits = list_habits(session, user_id)
    moved = [h for h in habits if h.category_id == category_id]
    if moved:
        if move_to is None or move_to == category_id:
            raise ValueError("Choose another category for its habits")
        end = max(h.sort_order for h in habits) + 1
        for i, h in enumerate(moved):  # keeps their order, at the end of the new category
            h.category_id = move_to
            h.sort_order = end + i
        session.flush()  # habits leave before the category row goes (FK)
    session.delete(category)
    session.commit()
    return category


def rename_category(session: Session, user_id: int, category_id: int, name: str) -> Category | None:
    category = _owned(session, Category, category_id, user_id)
    if category is None:
        return None
    category.name = name.strip()
    session.commit()
    return category


def list_notes(session: Session, user_id: int, kind: str) -> list[Note]:
    stmt = (
        select(Note)
        .where(Note.user_id == user_id, Note.kind == kind)
        .order_by(col(Note.sort_order), col(Note.id))
    )
    return list(session.exec(stmt))


def note_blocks(session: Session, user_id: int) -> list[tuple[str, str, list[Note]]]:
    """(kind, title, notes) for every note block, in display order."""
    return [(kind, title, list_notes(session, user_id, kind)) for kind, title in NOTE_KINDS.items()]


def create_note(session: Session, user_id: int, kind: str, text: str) -> Note:
    """Adds a note at the end of its block."""
    last = max((n.sort_order for n in list_notes(session, user_id, kind)), default=-1)
    note = Note(user_id=user_id, kind=kind, text=text.strip(), sort_order=last + 1)
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def update_note(session: Session, user_id: int, note_id: int, text: str) -> Note | None:
    note = _owned(session, Note, note_id, user_id)
    if note is None:
        return None
    note.text = text.strip()
    session.commit()
    return note


def reorder_notes(session: Session, user_id: int, order: dict[str, list[int]]) -> bool:
    """Stores the order of notes per block, moving notes between blocks as listed.

    `order` maps a kind to its note ids top to bottom (as dragged in the UI). Notes not listed
    keep their block and place. False if a kind or id is unknown or an id is listed twice.
    """
    ids = [i for kind_ids in order.values() for i in kind_ids]
    if not ids or len(set(ids)) != len(ids) or not set(order) <= set(NOTE_KINDS):
        return False
    stmt = select(Note).where(Note.user_id == user_id, col(Note.id).in_(ids))
    notes = {n.id: n for n in session.exec(stmt)}
    if len(notes) != len(ids):
        return False
    for kind, kind_ids in order.items():
        for pos, note_id in enumerate(kind_ids):
            notes[note_id].kind = kind
            notes[note_id].sort_order = pos
    session.commit()
    return True


def delete_note(session: Session, user_id: int, note_id: int) -> Note | None:
    note = _owned(session, Note, note_id, user_id)
    if note is None:
        return None
    session.delete(note)
    session.commit()
    return note


def set_highlight(
    session: Session, user_id: int, habit_id: int, highlight: str | None
) -> Habit | None:
    """Tints the habit's row; None clears it."""
    habit = _owned(session, Habit, habit_id, user_id)
    if habit is None:
        return None
    habit.highlight = highlight
    session.commit()
    return habit
