"""drop_highlight_tables

Revision ID: e6d13cc23848
Revises: e58dbaf9d182
Create Date: 2026-01-25 21:05:24.824082

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e6d13cc23848"
down_revision: str | Sequence[str] | None = "e58dbaf9d182"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop highlight_comment first due to FK constraint
    op.drop_table("highlight_comment")
    op.drop_index(op.f("ix_highlight_case_id"), table_name="highlight")
    op.drop_table("highlight")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "highlight_comment",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("highlight_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "author", sa.VARCHAR(length=100), autoincrement=False, nullable=False
        ),
        sa.Column("text", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["highlight_id"],
            ["highlight.id"],
            name=op.f("highlight_comment_highlight_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("highlight_comment_pkey")),
    )
    op.create_table(
        "highlight",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "case_id", sa.VARCHAR(length=255), autoincrement=False, nullable=False
        ),
        sa.Column("tag", sa.VARCHAR(length=50), autoincrement=False, nullable=False),
        sa.Column("start_offset", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("end_offset", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("text", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("para_num", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column(
            "section_header", sa.VARCHAR(length=200), autoincrement=False, nullable=True
        ),
        sa.Column(
            "created_by", sa.VARCHAR(length=100), autoincrement=False, nullable=False
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("highlight_pkey")),
    )
    op.create_index(
        op.f("ix_highlight_case_id"), "highlight", ["case_id"], unique=False
    )
    # ### end Alembic commands ###
