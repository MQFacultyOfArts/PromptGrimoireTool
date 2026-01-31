"""drop_workspace_created_by

Revision ID: 4ac592c459a3
Revises: fe6d5d784dab
Create Date: 2026-01-31 15:44:15.471360

Remove created_by from workspace table. Access control will be handled
via ACL (Seam D) rather than FK ownership. Workspaces are isolated silos;
ownership is a separate concern.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4ac592c459a3"
down_revision: str | Sequence[str] | None = "fe6d5d784dab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop created_by column and its FK/index from workspace table."""
    op.drop_index("ix_workspace_created_by", table_name="workspace")
    op.drop_constraint("workspace_created_by_fkey", "workspace", type_="foreignkey")
    op.drop_column("workspace", "created_by")


def downgrade() -> None:
    """Restore created_by column with FK to user table."""
    op.add_column(
        "workspace",
        sa.Column("created_by", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "workspace_created_by_fkey",
        "workspace",
        "user",
        ["created_by"],
        ["id"],
    )
    op.create_index("ix_workspace_created_by", "workspace", ["created_by"])
