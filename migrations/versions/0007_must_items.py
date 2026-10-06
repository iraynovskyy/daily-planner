"""must items

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-06 11:02:37.118402

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "mustitem",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("done_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], name="fk_mustitem_user_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("mustitem", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mustitem_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("mustitem", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mustitem_user_id"))
    op.drop_table("mustitem")
