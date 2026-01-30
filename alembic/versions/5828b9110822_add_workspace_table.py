"""add_workspace_table

Revision ID: 5828b9110822
Revises: 8da58dddd990
Create Date: 2026-01-31 10:40:34.221355

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5828b9110822"
down_revision: str | Sequence[str] | None = "8da58dddd990"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workspace",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("crdt_state", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_created_by", "workspace", ["created_by"])
    op.create_index("ix_workspace_updated_at", "workspace", ["updated_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_workspace_updated_at", table_name="workspace")
    op.drop_index("ix_workspace_created_by", table_name="workspace")
    op.drop_table("workspace")
