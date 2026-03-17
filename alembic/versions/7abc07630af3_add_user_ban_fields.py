"""add user ban fields

Revision ID: 7abc07630af3
Revises: 9eebaa40c9fd
Create Date: 2026-03-16 23:15:19.490088

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7abc07630af3"
down_revision: str | Sequence[str] | None = "9eebaa40c9fd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "user",
        sa.Column("is_banned", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "user", sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user", "banned_at")
    op.drop_column("user", "is_banned")
