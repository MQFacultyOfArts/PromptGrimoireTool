"""add sharing anonymity columns

Revision ID: ada0cc41422f
Revises: 1184bd94f104
Create Date: 2026-02-19 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ada0cc41422f"
down_revision: str | Sequence[str] | None = "1184bd94f104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add sharing/anonymity columns and peer permission row."""
    # Workspace columns
    op.add_column(
        "workspace",
        sa.Column("title", sa.Text(), nullable=True),
    )
    op.add_column(
        "workspace",
        sa.Column(
            "shared_with_class",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Activity column
    op.add_column(
        "activity",
        sa.Column("anonymous_sharing", sa.Boolean(), nullable=True),
    )

    # Course column
    op.add_column(
        "course",
        sa.Column(
            "default_anonymous_sharing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Seed peer permission row
    op.execute("INSERT INTO permission (name, level) VALUES ('peer', 15)")


def downgrade() -> None:
    """Remove sharing/anonymity columns and peer permission row."""
    op.execute("DELETE FROM permission WHERE name = 'peer'")
    op.drop_column("course", "default_anonymous_sharing")
    op.drop_column("activity", "anonymous_sharing")
    op.drop_column("workspace", "shared_with_class")
    op.drop_column("workspace", "title")
