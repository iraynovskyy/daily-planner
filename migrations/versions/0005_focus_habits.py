"""focus habits

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-30 12:10:41.505120

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("habit", schema=None) as batch_op:
        # No habit is in Focus until the user picks some.
        batch_op.add_column(
            sa.Column("focus", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("habit", schema=None) as batch_op:
        batch_op.drop_column("focus")
