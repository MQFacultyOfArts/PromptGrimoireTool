"""add color column to tag_group

Revision ID: ec22ee16be5d
Revises: 002b41705e53
Create Date: 2026-02-18 18:37:10.260764

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ec22ee16be5d"
down_revision: str | Sequence[str] | None = "002b41705e53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add optional color column to tag_group for toolbar background."""
    op.add_column(
        "tag_group",
        sa.Column("color", sa.String(length=7), nullable=True),
    )


def downgrade() -> None:
    """Remove color column from tag_group."""
    op.drop_column("tag_group", "color")
