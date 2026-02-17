"""add acl reference tables

Revision ID: 7c50e4641d69
Revises: 2b3157aeff45
Create Date: 2026-02-15 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c50e4641d69"
down_revision: str | Sequence[str] | None = "2b3157aeff45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create permission and course_role tables with seed data."""
    op.create_table(
        "permission",
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
        sa.UniqueConstraint("level", name="uq_permission_level"),
        sa.CheckConstraint("level BETWEEN 1 AND 100", name="ck_permission_level_range"),
    )

    op.create_table(
        "course_role",
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
        sa.UniqueConstraint("level", name="uq_course_role_level"),
        sa.CheckConstraint(
            "level BETWEEN 1 AND 100", name="ck_course_role_level_range"
        ),
    )

    # Seed reference data — these rows are the source of truth, not seed-data.
    op.execute("INSERT INTO permission (name, level) VALUES ('owner', 30)")
    op.execute("INSERT INTO permission (name, level) VALUES ('editor', 20)")
    op.execute("INSERT INTO permission (name, level) VALUES ('viewer', 10)")

    op.execute("INSERT INTO course_role (name, level) VALUES ('coordinator', 40)")
    op.execute("INSERT INTO course_role (name, level) VALUES ('instructor', 30)")
    op.execute("INSERT INTO course_role (name, level) VALUES ('tutor', 20)")
    op.execute("INSERT INTO course_role (name, level) VALUES ('student', 10)")


def downgrade() -> None:
    """Drop course_role and permission tables."""
    op.drop_table("course_role")
    op.drop_table("permission")
