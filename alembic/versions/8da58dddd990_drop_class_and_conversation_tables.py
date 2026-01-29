"""drop_class_and_conversation_tables

Revision ID: 8da58dddd990
Revises: e6d13cc23848
Create Date: 2026-01-29 21:38:22.141450

These tables were created in Spike 5 but superseded by:
- Class -> Course + CourseEnrollment (PR #60)
- Conversation -> CRDT-based AnnotationDocumentState

Neither table is used in application code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "8da58dddd990"
down_revision: str | Sequence[str] | None = "e6d13cc23848"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop unused Class and Conversation tables."""
    # Drop conversation first (has FK to class)
    # Use IF EXISTS since some test databases may be in inconsistent state
    op.execute("DROP INDEX IF EXISTS ix_conversation_owner_id")
    op.execute("DROP INDEX IF EXISTS ix_conversation_class_id")
    op.drop_table("conversation")

    # Then drop class
    op.execute("DROP INDEX IF EXISTS ix_class_owner_id")
    op.drop_table("class")


def downgrade() -> None:
    """Recreate Class and Conversation tables."""
    # Recreate class table
    op.create_table(
        "class",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "invite_code", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["user.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_code"),
    )
    op.create_index(op.f("ix_class_owner_id"), "class", ["owner_id"], unique=False)

    # Recreate conversation table
    op.create_table(
        "conversation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("class_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("raw_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("crdt_state", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["class.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["user.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversation_class_id"), "conversation", ["class_id"], unique=False
    )
    op.create_index(
        op.f("ix_conversation_owner_id"), "conversation", ["owner_id"], unique=False
    )
