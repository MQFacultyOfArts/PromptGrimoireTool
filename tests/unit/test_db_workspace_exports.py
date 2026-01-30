"""Tests for workspace-related db module exports."""

from __future__ import annotations


class TestWorkspaceExports:
    """Tests that workspace functions are exported."""

    def test_workspace_model_exported(self) -> None:
        """Workspace model is exported."""
        from promptgrimoire.db import Workspace

        assert Workspace is not None

    def test_workspace_document_model_exported(self) -> None:
        """WorkspaceDocument model is exported."""
        from promptgrimoire.db import WorkspaceDocument

        assert WorkspaceDocument is not None

    def test_create_workspace_exported(self) -> None:
        """create_workspace function is exported."""
        from promptgrimoire.db import create_workspace

        assert callable(create_workspace)

    def test_get_workspace_exported(self) -> None:
        """get_workspace function is exported."""
        from promptgrimoire.db import get_workspace

        assert callable(get_workspace)

    def test_delete_workspace_exported(self) -> None:
        """delete_workspace function is exported."""
        from promptgrimoire.db import delete_workspace

        assert callable(delete_workspace)

    def test_save_workspace_crdt_state_exported(self) -> None:
        """save_workspace_crdt_state function is exported."""
        from promptgrimoire.db import save_workspace_crdt_state

        assert callable(save_workspace_crdt_state)

    def test_add_document_exported(self) -> None:
        """add_document function is exported."""
        from promptgrimoire.db import add_document

        assert callable(add_document)

    def test_list_documents_exported(self) -> None:
        """list_documents function is exported."""
        from promptgrimoire.db import list_documents

        assert callable(list_documents)

    def test_reorder_documents_exported(self) -> None:
        """reorder_documents function is exported."""
        from promptgrimoire.db import reorder_documents

        assert callable(reorder_documents)
