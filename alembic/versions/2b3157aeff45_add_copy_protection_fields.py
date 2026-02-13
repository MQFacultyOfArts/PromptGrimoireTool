"""add copy protection fields

Revision ID: 2b3157aeff45
Revises: 3fe78447b221
Create Date: 2026-02-13 22:55:10.113954

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b3157aeff45"
down_revision: str | Sequence[str] | None = "3fe78447b221"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add copy_protection to Activity and default_copy_protection to Course."""
    op.add_column(
        "activity",
        sa.Column("copy_protection", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "course",
        sa.Column(
            "default_copy_protection",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove copy protection columns."""
    op.drop_column("course", "default_copy_protection")
    op.drop_column("activity", "copy_protection")
