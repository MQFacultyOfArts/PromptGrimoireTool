"""add source_document_id to workspace_document

Revision ID: 91eee643d54f
Revises: 6e7f4b2ac3e7
Create Date: 2026-03-02 21:39:07.310788

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "91eee643d54f"
down_revision: str | Sequence[str] | None = "6e7f4b2ac3e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add source_document_id FK to workspace_document for provenance tracking."""
    op.add_column(
        "workspace_document",
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_workspace_document_source_document_id",
        "workspace_document",
        ["source_document_id"],
    )
    op.create_foreign_key(
        "fk_workspace_document_source_document_id",
        "workspace_document",
        "workspace_document",
        ["source_document_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove source_document_id FK from workspace_document."""
    op.drop_constraint(
        "fk_workspace_document_source_document_id",
        "workspace_document",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_workspace_document_source_document_id",
        table_name="workspace_document",
    )
    op.drop_column("workspace_document", "source_document_id")
