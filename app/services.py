import calendar
import tomllib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from sqlmodel import Session, col, select

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
class CategoryMonth:
    category: Category
    habits: list[Habit]
    days: list[MonthDay]

    @property
    def progress(self) -> int:
        return progress([i for d in self.days for i in d.items])


def seed_default_habits(session: Session, seed_file: Path | None = None) -> None:
    """Fills an empty database with the categories, habits and notes from the seed TOML file."""
    if session.exec(select(Habit)).first() is not None:
        return
    with open(seed_file or settings.seed_path, "rb") as f:
        seed = tomllib.load(f)
    existing = {c.name: c for c in list_categories(session)}
    order = 0
    for cat_order, cat in enumerate(seed.get("category", [])):
        category = existing.get(cat["name"]) or Category(
            name=cat["name"], icon=cat.get("icon"), sort_order=cat_order
        )
        session.add(category)
        session.flush()
        for h in cat.get("habits", []):
            session.add(
                Habit(
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
        session.add(Note(kind=note["kind"], text=note["text"], sort_order=i))
    session.commit()


def list_categories(session: Session) -> list[Category]:
    return list(session.exec(select(Category).order_by(col(Category.sort_order), col(Category.id))))


def list_habits(session: Session, *, active_only: bool = False) -> list[Habit]:
    """Grouped by category; inside a category required habits come first, then optional ones."""
    stmt = (
        select(Habit)
        .join(Category)
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


def habits_by_category(session: Session) -> list[tuple[Category, list[Habit]]]:
    """Every category (even empty ones) with all its habits, for the settings page."""
    habits = list_habits(session)
    return [(c, [h for h in habits if h.category_id == c.id]) for c in list_categories(session)]


def day_by_category(session: Session, items: list[DayItem]) -> list[CategoryDay]:
    groups = [
        CategoryDay(c, [i for i in items if i.habit.category_id == c.id])
        for c in list_categories(session)
    ]
    return [g for g in groups if g.items]


def month_by_category(
    session: Session, habits: list[Habit], days: list[MonthDay]
) -> list[CategoryMonth]:
    """Splits a get_month() grid into one grid per category (same day list, fewer rows)."""
    groups = []
    for c in list_categories(session):
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


def _get_or_create_entry(session: Session, habit_id: int, day: date) -> DailyEntry:
    entry = session.exec(
        select(DailyEntry).where(DailyEntry.habit_id == habit_id, DailyEntry.date == day)
    ).first()
    if entry is None:
        entry = DailyEntry(habit_id=habit_id, date=day)
        session.add(entry)
    return entry


def get_day(session: Session, day: date) -> list[DayItem]:
    """Checklist for a day: active habits plus any inactive ones that already have history."""
    entries = {
        e.habit_id: e for e in session.exec(select(DailyEntry).where(DailyEntry.date == day))
    }
    items = []
    for habit in list_habits(session):
        entry = entries.get(habit.id)
        if entry is None:
            if not habit.active:
                continue
            entry = DailyEntry(habit_id=habit.id, date=day)
            session.add(entry)
        items.append(DayItem(habit, entry))
    session.commit()
    return items


def get_month(session: Session, year: int, month: int) -> tuple[list[Habit], list[MonthDay]]:
    """Checklist grid for a month: active habits plus inactive ones with progress in that month.

    Read-only: days without a stored entry get unsaved placeholders (count 0).
    """
    first = date(year, month, 1)
    last = first.replace(day=calendar.monthrange(year, month)[1])
    entries = session.exec(
        select(DailyEntry).where(DailyEntry.date >= first, DailyEntry.date <= last)
    ).all()
    by_key = {(e.habit_id, e.date): e for e in entries}
    with_history = {e.habit_id for e in entries if e.count_done > 0}
    habits = [h for h in list_habits(session) if h.active or h.id in with_history]
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


def set_count(session: Session, habit_id: int, day: date, count: int) -> DayItem | None:
    habit = session.get(Habit, habit_id)
    if habit is None:
        return None
    entry = _get_or_create_entry(session, habit_id, day)
    entry.count_done = max(0, min(count, habit.target_count))
    entry.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(entry)
    return DayItem(habit, entry)


def progress(items: list[DayItem]) -> int:
    """Completion % of required habits; optional ones are ignored."""
    items = [i for i in items if not i.habit.optional]
    total = sum(i.habit.target_count for i in items)
    done = sum(min(i.entry.count_done, i.habit.target_count) for i in items)
    return round(100 * done / total) if total else 0


def create_habit(
    session: Session,
    name: str,
    target_count: int,
    unit: str | None,
    optional: bool = False,
    category_id: int | None = None,
) -> Habit | None:
    """Adds a habit to `category_id` (default: first category); None if that category is unknown."""
    if category_id is None:
        category_id = list_categories(session)[0].id
    elif session.get(Category, category_id) is None:
        return None
    last = list_habits(session)
    habit = Habit(
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
    habit_id: int,
    name: str,
    target_count: int,
    unit: str | None,
    optional: bool = False,
    category_id: int | None = None,
) -> Habit | None:
    habit = session.get(Habit, habit_id)
    if habit is None or (category_id is not None and session.get(Category, category_id) is None):
        return None
    if category_id is not None and category_id != habit.category_id:
        # Moving to another category puts the habit at the end of it.
        habit.category_id = category_id
        habit.sort_order = max((h.sort_order for h in list_habits(session)), default=-1) + 1
    habit.name = name.strip()
    habit.target_count = max(1, min(target_count, 20))
    habit.unit = (unit or "").strip() or None
    habit.optional = optional
    session.commit()
    return habit


def set_active(session: Session, habit_id: int, active: bool) -> Habit | None:
    """Soft delete/restore — history in DailyEntry is always kept."""
    habit = session.get(Habit, habit_id)
    if habit is None:
        return None
    habit.active = active
    session.commit()
    return habit


def reorder_habits(session: Session, habit_ids: list[int]) -> bool:
    """Stores a new order for habits of one category (as dragged in the UI).

    `habit_ids` may be a subset of the category (pages hide inactive habits); the others keep
    their places. Required habits always stay above optional ones. False if the ids are
    unknown, repeated or span several categories.
    """
    habits = list_habits(session)
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


def create_category(session: Session, name: str) -> Category:
    last = list_categories(session)
    category = Category(name=name.strip(), sort_order=(last[-1].sort_order + 1) if last else 0)
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def rename_category(session: Session, category_id: int, name: str) -> Category | None:
    category = session.get(Category, category_id)
    if category is None:
        return None
    category.name = name.strip()
    session.commit()
    return category


def list_notes(session: Session, kind: str) -> list[Note]:
    stmt = select(Note).where(Note.kind == kind).order_by(col(Note.sort_order), col(Note.id))
    return list(session.exec(stmt))


def note_blocks(session: Session) -> list[tuple[str, str, list[Note]]]:
    """(kind, title, notes) for every note block, in display order."""
    return [(kind, title, list_notes(session, kind)) for kind, title in NOTE_KINDS.items()]


def create_note(session: Session, kind: str, text: str) -> Note:
    """Adds a note at the end of its block."""
    last = max((n.sort_order for n in list_notes(session, kind)), default=-1)
    note = Note(kind=kind, text=text.strip(), sort_order=last + 1)
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def update_note(session: Session, note_id: int, text: str) -> Note | None:
    note = session.get(Note, note_id)
    if note is None:
        return None
    note.text = text.strip()
    session.commit()
    return note


def reorder_notes(session: Session, order: dict[str, list[int]]) -> bool:
    """Stores the order of notes per block, moving notes between blocks as listed.

    `order` maps a kind to its note ids top to bottom (as dragged in the UI). Notes not listed
    keep their block and place. False if a kind or id is unknown or an id is listed twice.
    """
    ids = [i for kind_ids in order.values() for i in kind_ids]
    if not ids or len(set(ids)) != len(ids) or not set(order) <= set(NOTE_KINDS):
        return False
    notes = {n.id: n for n in session.exec(select(Note).where(col(Note.id).in_(ids)))}
    if len(notes) != len(ids):
        return False
    for kind, kind_ids in order.items():
        for pos, note_id in enumerate(kind_ids):
            notes[note_id].kind = kind
            notes[note_id].sort_order = pos
    session.commit()
    return True


def delete_note(session: Session, note_id: int) -> Note | None:
    note = session.get(Note, note_id)
    if note is None:
        return None
    session.delete(note)
    session.commit()
    return note


def set_highlight(session: Session, habit_id: int, highlight: str | None) -> Habit | None:
    """Tints the habit's row; None clears it."""
    habit = session.get(Habit, habit_id)
    if habit is None:
        return None
    habit.highlight = highlight
    session.commit()
    return habit
