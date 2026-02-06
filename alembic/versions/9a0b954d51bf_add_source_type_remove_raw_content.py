"""add_source_type_remove_raw_content

Revision ID: 9a0b954d51bf
Revises: 16f0dc427e7f
Create Date: 2026-02-05 12:27:14.047016

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a0b954d51bf"
down_revision: str | None = "16f0dc427e7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add source_type column, remove raw_content column."""
    # Add source_type column with default for existing rows
    op.add_column(
        "workspace_document",
        sa.Column(
            "source_type", sa.String(length=20), nullable=False, server_default="text"
        ),
    )
    # Remove the server default after adding (we want app to supply it)
    op.alter_column("workspace_document", "source_type", server_default=None)

    # Drop raw_content column
    op.drop_column("workspace_document", "raw_content")


def downgrade() -> None:
    """Restore raw_content column, remove source_type column."""
    # Add raw_content back (will be empty for new rows)
    op.add_column(
        "workspace_document",
        sa.Column("raw_content", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("workspace_document", "raw_content", server_default=None)

    # Drop source_type
    op.drop_column("workspace_document", "source_type")
