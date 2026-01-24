"""Database module for PromptGrimoire.

Provides async SQLModel operations with PostgreSQL.
"""

from __future__ import annotations

from promptgrimoire.db.annotation_state import get_state_by_case_id, save_state
from promptgrimoire.db.bootstrap import (
    get_expected_tables,
    is_db_configured,
    run_alembic_upgrade,
    verify_schema,
)
from promptgrimoire.db.engine import close_db, get_engine, get_session, init_db
from promptgrimoire.db.highlights import (
    MAX_COMMENT_LENGTH,
    CommentTooLongError,
    create_comment,
    create_highlight,
    delete_highlight,
    get_comments_for_highlight,
    get_highlight_by_id,
    get_highlights_for_case,
)
from promptgrimoire.db.models import (
    AnnotationDocumentState,
    Class,
    Conversation,
    Course,
    CourseEnrollment,
    CourseRole,
    Highlight,
    HighlightComment,
    User,
    Week,
)

__all__ = [
    "AnnotationDocumentState",
    "Class",
    "CommentTooLongError",
    "Conversation",
    "Course",
    "CourseEnrollment",
    "CourseRole",
    "Highlight",
    "HighlightComment",
    "MAX_COMMENT_LENGTH",
    "User",
    "Week",
    "close_db",
    "create_comment",
    "create_highlight",
    "delete_highlight",
    "get_comments_for_highlight",
    "get_engine",
    "get_expected_tables",
    "get_highlight_by_id",
    "get_highlights_for_case",
    "get_session",
    "get_state_by_case_id",
    "init_db",
    "is_db_configured",
    "run_alembic_upgrade",
    "save_state",
    "verify_schema",
]
