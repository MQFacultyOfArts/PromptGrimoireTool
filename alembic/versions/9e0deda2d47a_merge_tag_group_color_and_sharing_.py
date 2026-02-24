"""merge tag_group_color and sharing_anonymity heads

Revision ID: 9e0deda2d47a
Revises: 6eb4a98f77dc, ada0cc41422f
Create Date: 2026-02-23 12:47:23.732706

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "9e0deda2d47a"
down_revision: str | Sequence[str] | None = ("6eb4a98f77dc", "ada0cc41422f")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
