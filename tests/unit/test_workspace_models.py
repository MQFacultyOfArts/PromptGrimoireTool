"""Unit tests for Workspace and WorkspaceDocument models."""

from __future__ import annotations

from uuid import UUID


class TestWorkspaceModel:
    """Tests for Workspace model."""

    def test_workspace_has_default_uuid(self, make_workspace) -> None:
        """Workspace gets auto-generated UUID."""
        workspace = make_workspace()
        assert workspace.id is not None
        assert isinstance(workspace.id, UUID)

    def test_workspace_crdt_state_is_optional(self, make_workspace) -> None:
        """crdt_state can be None for new workspaces."""
        workspace = make_workspace()
        assert workspace.crdt_state is None

    def test_workspace_has_timestamps(self, make_workspace) -> None:
        """Workspace has created_at and updated_at."""
        workspace = make_workspace()
        assert workspace.created_at is not None
        assert workspace.updated_at is not None


class TestWorkspaceDocumentModel:
    """Tests for WorkspaceDocument model."""

    def test_document_has_default_uuid(self, make_workspace_document) -> None:
        """Document gets auto-generated UUID."""
        doc = make_workspace_document()
        assert doc.id is not None
        assert isinstance(doc.id, UUID)

    def test_document_requires_workspace_id(self, make_workspace_document) -> None:
        """Document must reference a workspace."""
        from uuid import uuid4

        workspace_id = uuid4()
        doc = make_workspace_document(workspace_id=workspace_id)
        assert doc.workspace_id == workspace_id

    def test_document_type_is_string(self, make_workspace_document) -> None:
        """Document type is a string (not enum)."""
        doc = make_workspace_document(type="source")
        assert doc.type == "source"
        assert isinstance(doc.type, str)

    def test_document_has_content_and_raw_content(
        self, make_workspace_document
    ) -> None:
        """Document stores both HTML content and raw content."""
        doc = make_workspace_document(
            content="<p><span>Hello</span></p>",
            raw_content="Hello",
        )
        assert doc.content == "<p><span>Hello</span></p>"
        assert doc.raw_content == "Hello"

    def test_document_has_order_index(self, make_workspace_document) -> None:
        """Document has order_index for display ordering."""
        doc = make_workspace_document(order_index=2)
        assert doc.order_index == 2

    def test_document_title_is_optional(self, make_workspace_document) -> None:
        """Document title can be None."""
        doc = make_workspace_document(title=None)
        assert doc.title is None
