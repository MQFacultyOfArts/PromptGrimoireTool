"""add_annotation_document_state

Revision ID: 5a677de22f52
Revises: 995de44465b7
Create Date: 2026-01-23 13:55:01.710380

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5a677de22f52"
down_revision: str | Sequence[str] | None = "995de44465b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "annotation_document_state",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.String(length=255), nullable=False),
        sa.Column("crdt_state", sa.LargeBinary(), nullable=False),
        sa.Column("highlight_count", sa.Integer(), nullable=False),
        sa.Column("last_editor", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_annotation_document_state_case_id",
        "annotation_document_state",
        ["case_id"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_annotation_document_state_case_id", table_name="annotation_document_state"
    )
    op.drop_table("annotation_document_state")
