import datetime as dt

from sqlmodel import Field, SQLModel, UniqueConstraint


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Category(SQLModel, table=True):
    """Group of habits with its own progress and dashboard (e.g. "Base", "Good habits")."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="app_user.id", index=True)
    name: str = Field(max_length=50)
    # Emoji shown in front of the category's timeline title, or None.
    icon: str | None = Field(default=None, max_length=10)
    sort_order: int = 0


class Habit(SQLModel, table=True):
    """Recurring template that appears on every day's checklist while active."""

    id: int | None = Field(default=None, primary_key=True)
    # Same owner as its category; stored here too so every query can filter on it directly.
    user_id: int = Field(foreign_key="app_user.id", index=True)
    name: str = Field(max_length=100)
    category_id: int = Field(foreign_key="category.id", index=True)
    target_count: int = Field(default=1, ge=1, le=20)
    unit: str | None = Field(default=None, max_length=20)
    sort_order: int = 0
    # Optional habits are shown for tracking but never count towards progress.
    optional: bool = False
    # Picked for the year page's "Focus" view (the few habits being worked on right now).
    focus: bool = False
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
    # A day the habit went beyond its target: shown as a gold star. Only kept while done.
    golden: bool = False
    updated_at: dt.datetime = Field(default_factory=_now)


class Note(SQLModel, table=True):
    """Free-text note shown in a collapsible block (kind: "tip" = Own Tips, "idea" = Ideas)."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="app_user.id", index=True)
    kind: str = Field(max_length=10, index=True)
    text: str = Field(max_length=300)
    sort_order: int = 0
    created_at: dt.datetime = Field(default_factory=_now)


class User(SQLModel, table=True):
    """A login. Only an argon2 hash of the password is stored, never the password."""

    # "user" is a reserved word in PostgreSQL, so the table gets a less clashing name.
    __tablename__ = "app_user"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(max_length=50, unique=True, index=True)
    password_hash: str = Field(max_length=200)
    created_at: dt.datetime = Field(default_factory=_now)


class Invite(SQLModel, table=True):
    """One-time sign-up link a user hands to a friend. Only a SHA-256 of the token is stored."""

    id: int | None = Field(default=None, primary_key=True)
    token_hash: str = Field(max_length=64, unique=True, index=True)
    created_by: int = Field(foreign_key="app_user.id", index=True)
    created_at: dt.datetime = Field(default_factory=_now)
    expires_at: dt.datetime
    used_at: dt.datetime | None = None
    used_by: int | None = Field(default=None, foreign_key="app_user.id")
