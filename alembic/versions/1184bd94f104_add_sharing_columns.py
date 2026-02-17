"""add sharing columns

Revision ID: 1184bd94f104
Revises: 064c301121d4
Create Date: 2026-02-16 20:59:38.356588

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1184bd94f104"
down_revision: str | Sequence[str] | None = "064c301121d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add sharing columns to course and activity tables."""
    op.add_column(
        "course",
        sa.Column(
            "default_allow_sharing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "activity",
        sa.Column("allow_sharing", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    """Remove sharing columns from course and activity tables."""
    op.drop_column("activity", "allow_sharing")
    op.drop_column("course", "default_allow_sharing")
