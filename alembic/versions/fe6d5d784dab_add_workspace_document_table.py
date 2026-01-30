"""add_workspace_document_table

Revision ID: fe6d5d784dab
Revises: 5828b9110822
Create Date: 2026-01-31 10:42:18.717010

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fe6d5d784dab"
down_revision: str | Sequence[str] | None = "5828b9110822"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workspace_document",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_document_workspace_id",
        "workspace_document",
        ["workspace_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_workspace_document_workspace_id", table_name="workspace_document")
    op.drop_table("workspace_document")
