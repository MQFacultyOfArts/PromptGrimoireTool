"""add is_staff to course_role

Revision ID: 064c301121d4
Revises: f7f6dd2b12c5
Create Date: 2026-02-15 18:43:02.993789

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "064c301121d4"
down_revision: str | Sequence[str] | None = "f7f6dd2b12c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add is_staff boolean to course_role and set values."""
    op.add_column(
        "course_role",
        sa.Column("is_staff", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Set staff flag for coordinator, instructor, tutor
    op.execute(
        "UPDATE course_role SET is_staff = true "
        "WHERE name IN ('coordinator', 'instructor', 'tutor')"
    )


def downgrade() -> None:
    """Remove is_staff column from course_role."""
    op.drop_column("course_role", "is_staff")
