"""Centralised exceptions for the DB layer.

All domain exceptions live here under BusinessLogicError, enabling the
UI to display meaningful error messages and get_session() to triage
log levels (expected business rejection vs unexpected failure).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID


class BusinessLogicError(Exception):
    """Base class for expected business logic rejections in the DB layer.

    Raised for anticipated user-facing error conditions (duplicate names,
    permission violations, protected resources). Distinguished from
    unexpected failures by get_session() for log-level triage.
    """


class SharePermissionError(BusinessLogicError):
    """Sharing policy violation.

    Non-owner share attempt, sharing disabled, or owner-grant attempt.
    """


class OwnershipError(BusinessLogicError):
    """Non-owner attempted an owner-only operation.

    For example, workspace or document deletion.
    """


class TagCreationDeniedError(BusinessLogicError):
    """Tag creation denied by placement context policy."""


class DeletionBlockedError(BusinessLogicError):
    """Raised when force=False and student workspaces exist under the target entity.

    Attributes:
        student_workspace_count: Number of student workspaces blocking deletion.
    """

    def __init__(self, student_workspace_count: int) -> None:
        self.student_workspace_count = student_workspace_count
        super().__init__(
            f"Deletion blocked: {student_workspace_count} student "
            f"workspace{'s' if student_workspace_count != 1 else ''} exist"
        )


class ProtectedDocumentError(BusinessLogicError):
    """Raised when attempting to delete a template-cloned document.

    Documents with a non-NULL source_document_id were cloned from a template
    and cannot be deleted by the user.

    Attributes:
        document_id: The document that was attempted to be deleted.
        source_document_id: The template document this was cloned from.
    """

    def __init__(self, document_id: UUID, source_document_id: UUID) -> None:
        self.document_id = document_id
        self.source_document_id = source_document_id
        super().__init__(
            f"Document {document_id} is a template clone "
            f"(source: {source_document_id}) and cannot be deleted"
        )


class DuplicateNameError(BusinessLogicError):
    """A tag or tag group with this name already exists.

    Raised instead of allowing IntegrityError to propagate through
    get_session()'s generic ERROR/Discord path.  Callers should
    catch this and present a user-friendly message.
    """


class TagLockedError(BusinessLogicError):
    """Tag modification denied because the tag or tag group is locked."""


class DuplicateCodenameError(BusinessLogicError):
    """A team codename already exists within one activity."""

    def __init__(self, activity_id: UUID, codename: str) -> None:
        self.activity_id = activity_id
        self.codename = codename
        super().__init__(
            f"Codename {codename!r} already exists in activity {activity_id}"
        )


class ZeroEditorError(BusinessLogicError):
    """Change would leave a team without any editable member."""

    def __init__(
        self,
        team_id: UUID,
        user_id: UUID,
        current_permission: str | None,
        attempted_permission: str | None,
    ) -> None:
        self.team_id = team_id
        self.user_id = user_id
        self.current_permission = current_permission
        self.attempted_permission = attempted_permission
        super().__init__(
            "Requested team permission change would leave "
            "the team without any member whose permission "
            "grants can_edit = TRUE"
        )


class DuplicateEnrollmentError(BusinessLogicError):
    """User is already enrolled in this course."""

    def __init__(self, course_id: UUID, user_id: UUID) -> None:
        self.course_id = course_id
        self.user_id = user_id
        super().__init__(f"User {user_id} is already enrolled in course {course_id}")


class StudentIdConflictError(BusinessLogicError):
    """User's existing student_id differs from the import."""

    def __init__(self, conflicts: list[tuple[str, str, str]]) -> None:
        self.conflicts = conflicts  # (email, existing_id, new_id)
        details = "; ".join(
            f"{email}: existing={old!r}, new={new!r}" for email, old, new in conflicts
        )
        super().__init__(f"Student ID conflicts: {details}")
