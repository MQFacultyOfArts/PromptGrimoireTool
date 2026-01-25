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
from promptgrimoire.db.courses import (
    DuplicateEnrollmentError,
    archive_course,
    create_course,
    enroll_user,
    get_course_by_id,
    get_enrollment,
    list_course_enrollments,
    list_courses,
    list_user_enrollments,
    unenroll_user,
    update_user_role,
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
from promptgrimoire.db.users import (
    create_user,
    find_or_create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_stytch_id,
    link_stytch_member,
    list_all_users,
    list_users,
    set_admin,
    update_display_name,
    update_last_login,
    upsert_user_on_login,
)

__all__ = [
    # Models
    "AnnotationDocumentState",
    "Class",
    "Conversation",
    "Course",
    "CourseEnrollment",
    "CourseRole",
    "Highlight",
    "HighlightComment",
    "User",
    "Week",
    # Exceptions
    "CommentTooLongError",
    "DuplicateEnrollmentError",
    # Constants
    "MAX_COMMENT_LENGTH",
    # Engine
    "close_db",
    "get_engine",
    "get_session",
    "init_db",
    # Bootstrap
    "get_expected_tables",
    "is_db_configured",
    "run_alembic_upgrade",
    "verify_schema",
    # Annotation state
    "get_state_by_case_id",
    "save_state",
    # Highlights
    "create_comment",
    "create_highlight",
    "delete_highlight",
    "get_comments_for_highlight",
    "get_highlight_by_id",
    "get_highlights_for_case",
    # Courses
    "archive_course",
    "create_course",
    "enroll_user",
    "get_course_by_id",
    "get_enrollment",
    "list_course_enrollments",
    "list_courses",
    "list_user_enrollments",
    "unenroll_user",
    "update_user_role",
    # Users
    "create_user",
    "find_or_create_user",
    "get_user_by_email",
    "get_user_by_id",
    "get_user_by_stytch_id",
    "link_stytch_member",
    "list_all_users",
    "list_users",
    "set_admin",
    "update_display_name",
    "update_last_login",
    "upsert_user_on_login",
]
