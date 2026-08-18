"""add promoted partial indices

Four EXPLAIN-verified partial indices promoted by the 2026-08-17 index
audit (docs/implementation-plans/2026-08-17-ty-bump-toolchain/
index-candidates.md §6): admin-id lookups, the two shared-with-class
navigator arms, and the search_dirty worker claim scan.

CREATE INDEX CONCURRENTLY cannot run inside Alembic's transaction, so
each create sits in an autocommit block. ``if_not_exists`` keeps the
migration idempotent against environments where the indices were
created manually during measurement.

Revision ID: c9d1e7a40b21
Revises: a1b2c3d4e5f6
Create Date: 2026-08-17 21:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d1e7a40b21"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the four promoted partial indices concurrently."""
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_user_is_admin_true",
            "user",
            ["id"],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=True,
            postgresql_where=sa.text("is_admin"),
        )
        op.create_index(
            "ix_workspace_activity_id_shared",
            "workspace",
            ["activity_id"],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=True,
            postgresql_where=sa.text("shared_with_class"),
        )
        op.create_index(
            "ix_workspace_course_id_shared",
            "workspace",
            ["course_id"],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=True,
            postgresql_where=sa.text("shared_with_class"),
        )
        op.create_index(
            "ix_workspace_search_dirty",
            "workspace",
            ["id"],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=True,
            postgresql_where=sa.text("search_dirty"),
        )


def downgrade() -> None:
    """Drop the four promoted partial indices."""
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_workspace_search_dirty",
            table_name="workspace",
            if_exists=True,
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_workspace_course_id_shared",
            table_name="workspace",
            if_exists=True,
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_workspace_activity_id_shared",
            table_name="workspace",
            if_exists=True,
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_user_is_admin_true",
            table_name="user",
            if_exists=True,
            postgresql_concurrently=True,
        )
