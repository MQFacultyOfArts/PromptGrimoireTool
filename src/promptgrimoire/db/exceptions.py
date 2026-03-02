"""Centralised exceptions for the DB layer.

Custom exceptions for delete guard logic, enabling the UI to display
meaningful error messages with counts and identifiers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID


class DeletionBlockedError(Exception):
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


class ProtectedDocumentError(Exception):
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
