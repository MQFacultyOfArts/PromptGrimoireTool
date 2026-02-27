"""add FTS infrastructure

Revision ID: 2cef9ec5dc10
Revises: 9e0deda2d47a
Create Date: 2026-02-25 15:20:09.850977

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2cef9ec5dc10"
down_revision: str | Sequence[str] | None = "9e0deda2d47a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add FTS columns and GIN expression indexes."""
    # Workspace columns for CRDT-sourced search text
    op.add_column(
        "workspace",
        sa.Column("search_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "workspace",
        sa.Column(
            "search_dirty",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # GIN expression index on workspace_document.content (HTML-stripped).
    # NOTE: If re-creating this index on a populated database, use
    # CREATE INDEX CONCURRENTLY to avoid a full table lock.  CONCURRENTLY
    # requires autocommit mode (run outside a transaction block) and cannot
    # be used inside an Alembic migration directly -- execute it manually
    # via psql with: CREATE INDEX CONCURRENTLY idx_workspace_document_fts ...
    op.execute(
        "CREATE INDEX idx_workspace_document_fts "
        "ON workspace_document "
        "USING gin(to_tsvector('english', "
        "regexp_replace(content, '<[^>]+>', ' ', 'g')))"
    )

    # GIN expression index on workspace.search_text (CRDT-sourced text).
    # Same CONCURRENTLY note applies -- see comment above.
    op.execute(
        "CREATE INDEX idx_workspace_search_text_fts "
        "ON workspace "
        "USING gin(to_tsvector('english', COALESCE(search_text, '')))"
    )


def downgrade() -> None:
    """Drop FTS indexes and columns."""
    op.execute("DROP INDEX IF EXISTS idx_workspace_search_text_fts")
    op.execute("DROP INDEX IF EXISTS idx_workspace_document_fts")
    op.drop_column("workspace", "search_dirty")
    op.drop_column("workspace", "search_text")
