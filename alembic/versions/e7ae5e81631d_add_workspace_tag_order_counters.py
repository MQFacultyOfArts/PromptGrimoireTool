"""add workspace tag order counters

Revision ID: e7ae5e81631d
Revises: ec22ee16be5d
Create Date: 2026-02-21 18:47:48.714269

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7ae5e81631d"
down_revision: str | Sequence[str] | None = "ec22ee16be5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add atomic counter columns for tag/group ordering."""
    op.add_column(
        "workspace",
        sa.Column("next_tag_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "workspace",
        sa.Column("next_group_order", sa.Integer(), nullable=False, server_default="0"),
    )

    # Data migration: populate from existing tag/group counts
    op.execute(
        """
        UPDATE workspace SET next_tag_order = (
            SELECT count(*) FROM tag WHERE tag.workspace_id = workspace.id
        )
        """
    )
    op.execute(
        """
        UPDATE workspace SET next_group_order = (
            SELECT count(*) FROM tag_group WHERE tag_group.workspace_id = workspace.id
        )
        """
    )


def downgrade() -> None:
    """Remove atomic counter columns."""
    op.drop_column("workspace", "next_group_order")
    op.drop_column("workspace", "next_tag_order")
