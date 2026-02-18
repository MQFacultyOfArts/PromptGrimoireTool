"""add tag tables and policy

Revision ID: 002b41705e53
Revises: 1184bd94f104
Create Date: 2026-02-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002b41705e53"
down_revision: str | Sequence[str] | None = "1184bd94f104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tag_group and tag tables, add tag creation policy columns."""
    # --- new tables ---
    op.create_table(
        "tag_group",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "tag",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column(
            "locked", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["tag_group.id"],
            ondelete="SET NULL",
        ),
    )

    # --- indexes on FK columns (PostgreSQL does not auto-create these) ---
    op.create_index("ix_tag_group_workspace_id", "tag_group", ["workspace_id"])
    op.create_index("ix_tag_workspace_id", "tag", ["workspace_id"])
    op.create_index("ix_tag_group_id", "tag", ["group_id"])

    # --- unique constraints ---
    op.create_unique_constraint(
        "uq_tag_group_workspace_name", "tag_group", ["workspace_id", "name"]
    )
    op.create_unique_constraint(
        "uq_tag_workspace_name", "tag", ["workspace_id", "name"]
    )

    # --- check constraint on color ---
    op.create_check_constraint("ck_tag_color_hex", "tag", "color ~ '^#[0-9a-fA-F]{6}$'")

    # --- policy columns ---
    op.add_column(
        "activity",
        sa.Column("allow_tag_creation", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "course",
        sa.Column(
            "default_allow_tag_creation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    """Drop tag tables and policy columns."""
    op.drop_column("course", "default_allow_tag_creation")
    op.drop_column("activity", "allow_tag_creation")
    op.drop_constraint("ck_tag_color_hex", "tag", type_="check")
    op.drop_constraint("uq_tag_workspace_name", "tag", type_="unique")
    op.drop_constraint("uq_tag_group_workspace_name", "tag_group", type_="unique")
    op.drop_index("ix_tag_group_id", table_name="tag")
    op.drop_index("ix_tag_workspace_id", table_name="tag")
    op.drop_index("ix_tag_group_workspace_id", table_name="tag_group")
    op.drop_table("tag")
    op.drop_table("tag_group")
