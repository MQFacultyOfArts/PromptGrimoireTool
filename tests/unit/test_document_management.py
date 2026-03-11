"""Unit tests for document management guard functions.

Tests verify pure logic for document edit eligibility.

Traceability:
- Issue: #109 (file upload)
- AC: file-upload-109.AC3.1, AC3.2
"""

from __future__ import annotations

from uuid import UUID

from promptgrimoire.pages.annotation.document_management import can_edit_document

# Fixed UUIDs for deterministic tests
_WORKSPACE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_TEMPLATE_SOURCE_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class TestCanEditDocument:
    """Verify document edit eligibility logic."""

    def test_editable_when_zero_annotations_and_user_uploaded(
        self, make_workspace_document
    ) -> None:
        """AC3.1: Document with no annotations and no source_document_id is editable."""
        doc = make_workspace_document(
            workspace_id=_WORKSPACE_ID,
            title="My Upload",
            source_document_id=None,
        )
        assert can_edit_document(doc, annotation_count=0) is True

    def test_not_editable_when_annotations_exist(self, make_workspace_document) -> None:
        """AC3.2: Document with annotations is not editable."""
        doc = make_workspace_document(
            workspace_id=_WORKSPACE_ID,
            title="Annotated Doc",
            source_document_id=None,
        )
        assert can_edit_document(doc, annotation_count=3) is False

    def test_not_editable_when_template_clone(self, make_workspace_document) -> None:
        """Template clone with zero annotations is not editable."""
        doc = make_workspace_document(
            workspace_id=_WORKSPACE_ID,
            title="Cloned Doc",
            source_document_id=_TEMPLATE_SOURCE_ID,
        )
        assert can_edit_document(doc, annotation_count=0) is False

    def test_not_editable_when_template_clone_with_annotations(
        self, make_workspace_document
    ) -> None:
        """Template clone with annotations is not editable (both conditions fail)."""
        doc = make_workspace_document(
            workspace_id=_WORKSPACE_ID,
            title="Cloned Annotated",
            source_document_id=_TEMPLATE_SOURCE_ID,
        )
        assert can_edit_document(doc, annotation_count=5) is False
