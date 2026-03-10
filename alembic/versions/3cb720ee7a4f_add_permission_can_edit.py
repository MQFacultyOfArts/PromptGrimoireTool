"""add permission can_edit

Revision ID: 3cb720ee7a4f
Revises: 1b59ab790954
Create Date: 2026-03-08 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3cb720ee7a4f"
down_revision: str | Sequence[str] | None = "1b59ab790954"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add can_edit classifier to permission and backfill seeded rows."""
    op.add_column(
        "permission",
        sa.Column("can_edit", sa.Boolean(), nullable=True, server_default="false"),
    )
    op.execute(
        "UPDATE permission SET can_edit = TRUE WHERE name IN ('owner', 'editor')"
    )
    op.execute(
        "UPDATE permission SET can_edit = FALSE WHERE name IN ('peer', 'viewer')"
    )
    op.alter_column(
        "permission",
        "can_edit",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default="false",
    )


def downgrade() -> None:
    """Remove can_edit classifier from permission."""
    op.drop_column("permission", "can_edit")
