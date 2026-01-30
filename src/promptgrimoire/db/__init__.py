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
from promptgrimoire.db.models import (
    AnnotationDocumentState,
    Course,
    CourseEnrollment,
    CourseRole,
    User,
    Week,
    Workspace,
    WorkspaceDocument,
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
from promptgrimoire.db.workspace_documents import (
    add_document,
    list_documents,
    reorder_documents,
)
from promptgrimoire.db.workspaces import (
    create_workspace,
    delete_workspace,
    get_workspace,
    save_workspace_crdt_state,
)

__all__ = [
    "AnnotationDocumentState",
    "Course",
    "CourseEnrollment",
    "CourseRole",
    "DuplicateEnrollmentError",
    "User",
    "Week",
    "Workspace",
    "WorkspaceDocument",
    "add_document",
    "archive_course",
    "close_db",
    "create_course",
    "create_user",
    "create_workspace",
    "delete_workspace",
    "enroll_user",
    "find_or_create_user",
    "get_course_by_id",
    "get_engine",
    "get_enrollment",
    "get_expected_tables",
    "get_session",
    "get_state_by_case_id",
    "get_user_by_email",
    "get_user_by_id",
    "get_user_by_stytch_id",
    "get_workspace",
    "init_db",
    "is_db_configured",
    "link_stytch_member",
    "list_all_users",
    "list_course_enrollments",
    "list_courses",
    "list_documents",
    "list_user_enrollments",
    "list_users",
    "reorder_documents",
    "run_alembic_upgrade",
    "save_state",
    "save_workspace_crdt_state",
    "set_admin",
    "unenroll_user",
    "update_display_name",
    "update_last_login",
    "update_user_role",
    "upsert_user_on_login",
    "verify_schema",
]
