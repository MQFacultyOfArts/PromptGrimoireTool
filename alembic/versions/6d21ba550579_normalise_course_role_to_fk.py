"""normalise course role to fk

Revision ID: 6d21ba550579
Revises: 7c50e4641d69
Create Date: 2026-02-15 13:51:25.497279

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d21ba550579"
down_revision: str | Sequence[str] | None = "7c50e4641d69"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert CourseEnrollment.role from PG enum to VARCHAR FK on course_role."""
    # 1. Convert column type from PG enum to varchar
    op.alter_column(
        "course_enrollment",
        "role",
        type_=sa.String(50),
        existing_type=sa.Enum(
            "coordinator", "instructor", "tutor", "student", name="courserole"
        ),
        postgresql_using="role::text",
    )

    # 2. Add FK constraint to course_role reference table
    op.create_foreign_key(
        "fk_course_enrollment_role",
        "course_enrollment",
        "course_role",
        ["role"],
        ["name"],
        ondelete="RESTRICT",
    )

    # 3. Drop the PG enum type (no longer needed)
    op.execute("DROP TYPE courserole")


def downgrade() -> None:
    """Revert to PG enum for CourseEnrollment.role."""
    # 1. Drop the FK constraint
    op.drop_constraint(
        "fk_course_enrollment_role", "course_enrollment", type_="foreignkey"
    )

    # 2. Recreate the PG enum type
    courserole = sa.Enum(
        "coordinator", "instructor", "tutor", "student", name="courserole"
    )
    courserole.create(op.get_bind())

    # 3. Convert column type back to PG enum
    op.alter_column(
        "course_enrollment",
        "role",
        type_=courserole,
        existing_type=sa.String(50),
        postgresql_using="role::courserole",
    )
