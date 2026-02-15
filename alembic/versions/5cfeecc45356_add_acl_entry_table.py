"""add acl entry table

Revision ID: 5cfeecc45356
Revises: 6d21ba550579
Create Date: 2026-02-15 14:52:01.091767

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5cfeecc45356"
down_revision: str | Sequence[str] | None = "6d21ba550579"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create acl_entry table with FKs and unique constraint."""
    op.create_table(
        "acl_entry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("permission", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["permission"], ["permission.name"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "workspace_id", "user_id", name="uq_acl_entry_workspace_user"
        ),
    )
    # Index on user_id for "list entries for user" queries
    op.create_index("ix_acl_entry_user_id", "acl_entry", ["user_id"])


def downgrade() -> None:
    """Drop acl_entry table and its index."""
    op.drop_index("ix_acl_entry_user_id", table_name="acl_entry")
    op.drop_table("acl_entry")
