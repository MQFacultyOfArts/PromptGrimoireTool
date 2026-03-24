"""Unit tests for document management section in the Organise tab.

Tests verify pure logic for document delete eligibility and document
listing behaviour in the Organise tab.

Traceability:
- Design: docs/implementation-plans/2026-03-02-crud-management-229/phase_07.md Tasks 2-3
- AC: crud-management-229.AC4.1, AC4.3, AC5.5
- AC: tag-deletion-guards-413.AC3.4
"""

from __future__ import annotations

from uuid import UUID

from promptgrimoire.pages.annotation.document_management import can_delete_document

# Fixed UUIDs for deterministic tests
_OWNER_WORKSPACE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_TEMPLATE_SOURCE_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class TestCanDeleteDocument:
    """Verify document delete eligibility logic (AC4.3, AC3.4)."""

    def test_owner_can_delete_user_uploaded_document(
        self, make_workspace_document
    ) -> None:
        """Owner can delete a document with no source and no annotations."""
        doc = make_workspace_document(
            workspace_id=_OWNER_WORKSPACE_ID,
            title="My Upload",
            source_document_id=None,
        )
        assert can_delete_document(doc, is_owner=True, annotation_count=0) is True

    def test_owner_cannot_delete_template_cloned_document(
        self, make_workspace_document
    ) -> None:
        """Owner cannot delete a template-cloned document (AC4.3)."""
        doc = make_workspace_document(
            workspace_id=_OWNER_WORKSPACE_ID,
            title="Cloned Doc",
            source_document_id=_TEMPLATE_SOURCE_ID,
        )
        assert can_delete_document(doc, is_owner=True, annotation_count=0) is False

    def test_non_owner_cannot_delete_any_document(
        self, make_workspace_document
    ) -> None:
        """Non-owners never see delete buttons, even for user-uploaded docs."""
        doc = make_workspace_document(
            workspace_id=_OWNER_WORKSPACE_ID,
            title="User Upload",
            source_document_id=None,
        )
        assert can_delete_document(doc, is_owner=False, annotation_count=0) is False

    def test_non_owner_cannot_delete_template_document(
        self, make_workspace_document
    ) -> None:
        """Non-owners cannot delete template-cloned documents either."""
        doc = make_workspace_document(
            workspace_id=_OWNER_WORKSPACE_ID,
            title="Template Doc",
            source_document_id=_TEMPLATE_SOURCE_ID,
        )
        assert can_delete_document(doc, is_owner=False, annotation_count=0) is False

    def test_owner_cannot_delete_document_with_annotations(
        self, make_workspace_document
    ) -> None:
        """AC3.4: Document with annotations is not deletable even by owner."""
        doc = make_workspace_document(
            workspace_id=_OWNER_WORKSPACE_ID,
            title="Annotated Doc",
            source_document_id=None,
        )
        assert can_delete_document(doc, is_owner=True, annotation_count=3) is False
