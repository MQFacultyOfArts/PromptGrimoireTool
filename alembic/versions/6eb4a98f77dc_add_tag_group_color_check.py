"""add tag group color check

Revision ID: 6eb4a98f77dc
Revises: e7ae5e81631d
Create Date: 2026-02-22 13:48:39.749380

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6eb4a98f77dc"
down_revision: str | Sequence[str] | None = "e7ae5e81631d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add CHECK constraint on tag_group.color for valid hex or NULL."""
    # Assert no existing invalid data before adding the constraint
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT count(*) FROM tag_group "
            "WHERE color IS NOT NULL AND color !~ '^#[0-9a-fA-F]{6}$'"
        )
    )
    bad_count = result.scalar()
    if bad_count is not None and bad_count > 0:
        msg = (
            f"Cannot add CHECK constraint: {bad_count} tag_group rows "
            f"have invalid color values. Fix data first."
        )
        raise RuntimeError(msg)

    op.create_check_constraint(
        "ck_tag_group_color_hex",
        "tag_group",
        "color IS NULL OR color ~ '^#[0-9a-fA-F]{6}$'",
    )


def downgrade() -> None:
    """Remove CHECK constraint on tag_group.color."""
    op.drop_constraint("ck_tag_group_color_hex", "tag_group", type_="check")
