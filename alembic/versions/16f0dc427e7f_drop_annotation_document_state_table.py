"""drop_annotation_document_state_table

Revision ID: 16f0dc427e7f
Revises: 4ac592c459a3
Create Date: 2026-02-01 12:19:12.806602

BREAKING: Old annotation data is no longer accessible.
Workspace model is now the only persistence mechanism.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "16f0dc427e7f"
down_revision: str | Sequence[str] | None = "4ac592c459a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the old annotation_document_state table.

    This completes the migration to the workspace model.
    The annotation_document_state table is no longer needed.
    """
    op.drop_index(
        "ix_annotation_document_state_case_id", table_name="annotation_document_state"
    )
    op.drop_table("annotation_document_state")


def downgrade() -> None:
    """Recreate annotation_document_state table.

    WARNING: This does not restore data - only recreates the schema.
    """
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
