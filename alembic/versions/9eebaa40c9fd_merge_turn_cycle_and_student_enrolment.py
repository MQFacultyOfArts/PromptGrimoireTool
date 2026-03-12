"""merge turn cycle and student enrolment

Revision ID: 9eebaa40c9fd
Revises: 0405a9085ccf, f8df8cfbeeb6
Create Date: 2026-03-12 20:57:53.036265

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "9eebaa40c9fd"
down_revision: str | Sequence[str] | None = ("0405a9085ccf", "f8df8cfbeeb6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
