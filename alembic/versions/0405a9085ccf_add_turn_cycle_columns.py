"""add turn cycle columns

Revision ID: 0405a9085ccf
Revises: 3cb720ee7a4f
Create Date: 2026-03-11 23:44:41.434025

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0405a9085ccf"
down_revision: str | Sequence[str] | None = "3cb720ee7a4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "wargame_config",
        sa.Column(
            "summary_system_prompt", sa.Text(), server_default="", nullable=False
        ),
    )
    op.add_column(
        "wargame_team",
        sa.Column("move_buffer_crdt", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "wargame_team",
        sa.Column("notes_crdt", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("wargame_config", "summary_system_prompt")
    op.drop_column("wargame_team", "notes_crdt")
    op.drop_column("wargame_team", "move_buffer_crdt")
