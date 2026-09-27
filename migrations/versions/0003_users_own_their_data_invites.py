"""users own their data; invites

Categories, habits and notes get a user_id. Existing rows go to the first user (the owner of the
single-user planner). Daily entries belong to a user through their habit.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27 20:55:55.338738

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNED = ("category", "habit", "note")


def _assign_existing_rows() -> None:
    conn = op.get_bind()
    owner = conn.execute(sa.text("SELECT MIN(id) FROM app_user")).scalar()
    if owner is None:
        # No user yet: only the untouched starter set can exist, since nothing is reachable
        # without a login. Drop it; users now get their own starter set when they're created.
        if conn.execute(sa.text("SELECT COUNT(*) FROM dailyentry WHERE count_done > 0")).scalar():
            raise RuntimeError(
                "Habit history exists but there is no user to own it. Create one first "
                "(python -m app.create_user <name>) on revision 0002, then upgrade again."
            )
        for table in ("dailyentry", "habit", "category", "note"):
            conn.execute(sa.text(f"DELETE FROM {table}"))
        return
    for table in OWNED:
        conn.execute(sa.text(f"UPDATE {table} SET user_id = :owner"), {"owner": owner})


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "invite",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("expires_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("used_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
        sa.Column("used_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["used_by"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("invite", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_invite_created_by"), ["created_by"], unique=False)
        batch_op.create_index(batch_op.f("ix_invite_token_hash"), ["token_hash"], unique=True)

    # Add as nullable, fill in, then make it required.
    for table in OWNED:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
    _assign_existing_rows()
    for table in OWNED:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
            batch_op.create_index(batch_op.f(f"ix_{table}_user_id"), ["user_id"], unique=False)
            batch_op.create_foreign_key(f"fk_{table}_user_id", "app_user", ["user_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema. Every user's rows stay, but they're no longer told apart."""
    for table in reversed(OWNED):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_user_id", type_="foreignkey")
            batch_op.drop_index(batch_op.f(f"ix_{table}_user_id"))
            batch_op.drop_column("user_id")

    with op.batch_alter_table("invite", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invite_token_hash"))
        batch_op.drop_index(batch_op.f("ix_invite_created_by"))
    op.drop_table("invite")
