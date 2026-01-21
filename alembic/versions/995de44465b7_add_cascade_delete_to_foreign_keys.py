"""add cascade delete to foreign keys

Revision ID: 995de44465b7
Revises: 59d4ef6caf5d
Create Date: 2026-01-21 13:15:21.178002

Adds ON DELETE CASCADE to foreign key constraints so that:
- Deleting a User cascades to their Classes and Conversations
- Deleting a Class cascades to its Conversations

This fixes HIGH-9 from the code review.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "995de44465b7"
down_revision: str | Sequence[str] | None = "59d4ef6caf5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ON DELETE CASCADE to foreign key constraints."""
    # class.owner_id -> user.id
    op.drop_constraint("class_owner_id_fkey", "class", type_="foreignkey")
    op.create_foreign_key(
        "class_owner_id_fkey",
        "class",
        "user",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # conversation.class_id -> class.id
    op.drop_constraint("conversation_class_id_fkey", "conversation", type_="foreignkey")
    op.create_foreign_key(
        "conversation_class_id_fkey",
        "conversation",
        "class",
        ["class_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # conversation.owner_id -> user.id
    op.drop_constraint("conversation_owner_id_fkey", "conversation", type_="foreignkey")
    op.create_foreign_key(
        "conversation_owner_id_fkey",
        "conversation",
        "user",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Remove CASCADE from foreign key constraints."""
    # conversation.owner_id -> user.id
    op.drop_constraint("conversation_owner_id_fkey", "conversation", type_="foreignkey")
    op.create_foreign_key(
        "conversation_owner_id_fkey",
        "conversation",
        "user",
        ["owner_id"],
        ["id"],
    )

    # conversation.class_id -> class.id
    op.drop_constraint("conversation_class_id_fkey", "conversation", type_="foreignkey")
    op.create_foreign_key(
        "conversation_class_id_fkey",
        "conversation",
        "class",
        ["class_id"],
        ["id"],
    )

    # class.owner_id -> user.id
    op.drop_constraint("class_owner_id_fkey", "class", type_="foreignkey")
    op.create_foreign_key(
        "class_owner_id_fkey",
        "class",
        "user",
        ["owner_id"],
        ["id"],
    )
