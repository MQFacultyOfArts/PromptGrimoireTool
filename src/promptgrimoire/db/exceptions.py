"""Centralised exceptions for the DB layer.

Custom exceptions for delete guard logic, enabling the UI to display
meaningful error messages with counts and identifiers.
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
