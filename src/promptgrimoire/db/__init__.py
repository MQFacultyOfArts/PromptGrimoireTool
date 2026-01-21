"""Database module for PromptGrimoire.

Provides async SQLModel operations with PostgreSQL.
"""

from __future__ import annotations

from promptgrimoire.db.engine import close_db, get_engine, get_session, init_db
from promptgrimoire.db.highlights import (
    create_comment,
    create_highlight,
    delete_highlight,
    get_comments_for_highlight,
    get_highlight_by_id,
    get_highlights_for_case,
)
from promptgrimoire.db.models import (
    Class,
    Conversation,
    Highlight,
    HighlightComment,
    User,
)

__all__ = [
    "Class",
    "Conversation",
    "Highlight",
    "HighlightComment",
    "User",
    "close_db",
    "create_comment",
    "create_highlight",
    "delete_highlight",
    "get_comments_for_highlight",
    "get_engine",
    "get_highlight_by_id",
    "get_highlights_for_case",
    "get_session",
    "init_db",
]
