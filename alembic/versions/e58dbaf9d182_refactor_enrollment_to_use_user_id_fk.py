"""Refactor enrollment to use user_id FK.

Revision ID: e58dbaf9d182
Revises: a124e721864c
Create Date: 2026-01-24

This migration:
1. Adds is_admin and last_login columns to user table
2. Drops member_id from course_enrollment
3. Adds user_id FK to course_enrollment
4. Updates unique constraint

Note: This is a breaking change. Existing enrollments are dropped
because they reference Stytch member_id strings, not local user UUIDs.
Re-enrollment is required after migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e58dbaf9d182"
down_revision: str | None = "a124e721864c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add new columns to user table
    op.add_column(
        "user",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "user", sa.Column("last_login", sa.DateTime(timezone=True), nullable=True)
    )

    # Remove server default after adding column
    op.alter_column("user", "is_admin", server_default=None)

    # Drop old constraint and column from course_enrollment
    op.drop_constraint(
        "uq_course_enrollment_course_member", "course_enrollment", type_="unique"
    )
    op.drop_index("ix_course_enrollment_member_id", table_name="course_enrollment")
    op.drop_column("course_enrollment", "member_id")

    # Add new user_id FK column
    op.add_column(
        "course_enrollment",
        sa.Column("user_id", sa.Uuid(), nullable=False),
    )
    op.create_foreign_key(
        "fk_course_enrollment_user_id",
        "course_enrollment",
        "user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_course_enrollment_user_id", "course_enrollment", ["user_id"])
    op.create_unique_constraint(
        "uq_course_enrollment_course_user",
        "course_enrollment",
        ["course_id", "user_id"],
    )


def downgrade() -> None:
    # Drop new user_id FK and constraints
    op.drop_constraint(
        "uq_course_enrollment_course_user", "course_enrollment", type_="unique"
    )
    op.drop_index("ix_course_enrollment_user_id", table_name="course_enrollment")
    op.drop_constraint(
        "fk_course_enrollment_user_id", "course_enrollment", type_="foreignkey"
    )
    op.drop_column("course_enrollment", "user_id")

    # Re-add member_id column
    op.add_column(
        "course_enrollment",
        sa.Column("member_id", sa.String(length=100), nullable=False),
    )
    op.create_index(
        "ix_course_enrollment_member_id", "course_enrollment", ["member_id"]
    )
    op.create_unique_constraint(
        "uq_course_enrollment_course_member",
        "course_enrollment",
        ["course_id", "member_id"],
    )

    # Drop new columns from user
    op.drop_column("user", "last_login")
    op.drop_column("user", "is_admin")
