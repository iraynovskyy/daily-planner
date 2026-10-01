"""user language

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-02 18:20:11.402113

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        # None: no choice made yet (the browser's language decides).
        batch_op.add_column(
            sa.Column("language", sqlmodel.sql.sqltypes.AutoString(length=5), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.drop_column("language")
