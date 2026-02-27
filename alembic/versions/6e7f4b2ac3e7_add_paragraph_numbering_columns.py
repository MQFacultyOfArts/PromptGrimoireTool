"""add paragraph numbering columns

Revision ID: 6e7f4b2ac3e7
Revises: 2cef9ec5dc10
Create Date: 2026-02-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6e7f4b2ac3e7"
down_revision: str | Sequence[str] | None = "2cef9ec5dc10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add paragraph numbering columns to workspace_document."""
    op.add_column(
        "workspace_document",
        sa.Column(
            "auto_number_paragraphs",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "workspace_document",
        sa.Column(
            "paragraph_map",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    """Drop paragraph numbering columns from workspace_document."""
    op.drop_column("workspace_document", "paragraph_map")
    op.drop_column("workspace_document", "auto_number_paragraphs")
