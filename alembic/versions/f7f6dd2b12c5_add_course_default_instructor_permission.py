"""add course default instructor permission

Revision ID: f7f6dd2b12c5
Revises: 5cfeecc45356
Create Date: 2026-02-15 18:19:48.249729

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7f6dd2b12c5"
down_revision: str | Sequence[str] | None = "5cfeecc45356"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add default_instructor_permission column to course table."""
    op.add_column(
        "course",
        sa.Column(
            "default_instructor_permission",
            sa.String(50),
            sa.ForeignKey("permission.name", ondelete="RESTRICT"),
            nullable=False,
            server_default="editor",
        ),
    )


def downgrade() -> None:
    """Remove default_instructor_permission column from course table."""
    op.drop_column("course", "default_instructor_permission")
