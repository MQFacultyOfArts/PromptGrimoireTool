"""add word count fields

Revision ID: b0f92eaf26aa
Revises: 6e7f4b2ac3e7
Create Date: 2026-03-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b0f92eaf26aa"
down_revision: str | Sequence[str] | None = "6e7f4b2ac3e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add word count fields to activity and course tables."""
    op.add_column("activity", sa.Column("word_minimum", sa.Integer(), nullable=True))
    op.add_column("activity", sa.Column("word_limit", sa.Integer(), nullable=True))
    op.add_column(
        "activity",
        sa.Column("word_limit_enforcement", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "course",
        sa.Column(
            "default_word_limit_enforcement",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Remove word count fields from activity and course tables."""
    op.drop_column("course", "default_word_limit_enforcement")
    op.drop_column("activity", "word_limit_enforcement")
    op.drop_column("activity", "word_limit")
    op.drop_column("activity", "word_minimum")
