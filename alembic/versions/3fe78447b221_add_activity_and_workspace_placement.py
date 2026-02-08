"""add activity and workspace placement

Revision ID: 3fe78447b221
Revises: 9a0b954d51bf
Create Date: 2026-02-08 11:49:22.479659

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3fe78447b221"
down_revision: str | Sequence[str] | None = "9a0b954d51bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add activity table and workspace placement columns."""
    # 1. Create activity table
    op.create_table(
        "activity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("week_id", sa.Uuid(), nullable=False),
        sa.Column("template_workspace_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["week_id"], ["week.id"], name="fk_activity_week_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["template_workspace_id"],
            ["workspace.id"],
            name="fk_activity_template_workspace_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_workspace_id"),
    )
    op.create_index("ix_activity_week_id", "activity", ["week_id"])

    # 2. Add placement columns to workspace
    op.add_column("workspace", sa.Column("activity_id", sa.Uuid(), nullable=True))
    op.add_column("workspace", sa.Column("course_id", sa.Uuid(), nullable=True))
    op.add_column(
        "workspace",
        sa.Column(
            "enable_save_as_draft", sa.Boolean(), nullable=False, server_default="false"
        ),
    )

    # 3. Add FK constraints on workspace placement columns
    op.create_foreign_key(
        "fk_workspace_activity_id",
        "workspace",
        "activity",
        ["activity_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_workspace_course_id",
        "workspace",
        "course",
        ["course_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 4. Add indexes on FK columns
    op.create_index("ix_workspace_activity_id", "workspace", ["activity_id"])
    op.create_index("ix_workspace_course_id", "workspace", ["course_id"])

    # 5. CHECK constraint: activity_id and course_id are mutually exclusive
    op.create_check_constraint(
        "ck_workspace_placement_exclusivity",
        "workspace",
        "NOT (activity_id IS NOT NULL AND course_id IS NOT NULL)",
    )


def downgrade() -> None:
    """Remove activity table and workspace placement columns."""
    # Reverse order of upgrade
    op.drop_constraint("ck_workspace_placement_exclusivity", "workspace", type_="check")
    op.drop_index("ix_workspace_course_id", table_name="workspace")
    op.drop_index("ix_workspace_activity_id", table_name="workspace")
    op.drop_constraint("fk_workspace_course_id", "workspace", type_="foreignkey")
    op.drop_constraint("fk_workspace_activity_id", "workspace", type_="foreignkey")
    op.drop_column("workspace", "enable_save_as_draft")
    op.drop_column("workspace", "course_id")
    op.drop_column("workspace", "activity_id")
    op.drop_index("ix_activity_week_id", table_name="activity")
    op.drop_table("activity")
