import datetime as dt

from sqlmodel import Field, SQLModel, UniqueConstraint


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Category(SQLModel, table=True):
    """Group of habits with its own progress and dashboard (e.g. "Base", "Good habits")."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=50)
    # Emoji shown in front of the category's timeline title, or None.
    icon: str | None = Field(default=None, max_length=10)
    sort_order: int = 0


class Habit(SQLModel, table=True):
    """Recurring template that appears on every day's checklist while active."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    category_id: int = Field(foreign_key="category.id", index=True)
    target_count: int = Field(default=1, ge=1, le=20)
    unit: str | None = Field(default=None, max_length=20)
    sort_order: int = 0
    # Optional habits are shown for tracking but never count towards progress.
    optional: bool = False
    # Row highlight colour picked in the UI (one of services.HIGHLIGHTS), or None.
    highlight: str | None = Field(default=None, max_length=10)
    active: bool = True
    created_at: dt.datetime = Field(default_factory=_now)


class DailyEntry(SQLModel, table=True):
    """Progress of one habit on one calendar day."""

    __table_args__ = (UniqueConstraint("habit_id", "date"),)

    id: int | None = Field(default=None, primary_key=True)
    habit_id: int = Field(foreign_key="habit.id", index=True)
    date: dt.date = Field(index=True)
    count_done: int = 0
    updated_at: dt.datetime = Field(default_factory=_now)


class Note(SQLModel, table=True):
    """Free-text note shown in a collapsible block (kind: "tip" = Own Tips, "idea" = Ideas)."""

    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(max_length=10, index=True)
    text: str = Field(max_length=300)
    sort_order: int = 0
    created_at: dt.datetime = Field(default_factory=_now)
