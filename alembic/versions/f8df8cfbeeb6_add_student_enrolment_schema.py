"""add student enrolment schema

Revision ID: f8df8cfbeeb6
Revises: 3cb720ee7a4f
Create Date: 2026-03-12 18:20:41.989838

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8df8cfbeeb6"
down_revision: str | Sequence[str] | None = "3cb720ee7a4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add student_id to user table
    op.add_column(
        "user",
        sa.Column("student_id", sa.String(50), nullable=True),
    )
    op.create_unique_constraint("uq_user_student_id", "user", ["student_id"])

    # Create student_group table
    op.create_table(
        "student_group",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["course.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("course_id", "name", name="uq_student_group_course_name"),
    )
    op.create_index(
        "ix_student_group_course_id",
        "student_group",
        ["course_id"],
    )

    # Create student_group_membership table
    op.create_table(
        "student_group_membership",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_group_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["student_group_id"],
            ["student_group.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "student_group_id",
            "user_id",
            name="uq_student_group_membership_group_user",
        ),
    )
    op.create_index(
        "ix_student_group_membership_student_group_id",
        "student_group_membership",
        ["student_group_id"],
    )
    op.create_index(
        "ix_student_group_membership_user_id",
        "student_group_membership",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_table("student_group_membership")
    op.drop_table("student_group")
    op.drop_constraint("uq_user_student_id", "user", type_="unique")
    op.drop_column("user", "student_id")
