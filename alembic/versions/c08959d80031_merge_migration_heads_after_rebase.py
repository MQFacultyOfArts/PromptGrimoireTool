"""merge migration heads after rebase

Revision ID: c08959d80031
Revises: 91eee643d54f, b0f92eaf26aa
Create Date: 2026-03-03 22:57:41.620302

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "c08959d80031"
down_revision: str | Sequence[str] | None = ("91eee643d54f", "b0f92eaf26aa")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
