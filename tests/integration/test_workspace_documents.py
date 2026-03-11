"""Integration tests for workspace document CRUD operations.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Covers:
- file-upload-109.AC3.1: update_document_content() persists new HTML
- file-upload-109.AC3.3: paragraph_map rebuilt consistently after update
"""

from __future__ import annotations

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestUpdateDocumentContent:
    """Tests for update_document_content()."""

    @pytest.mark.asyncio
    async def test_updates_content_in_db(self) -> None:
        """AC3.1: Content is persisted after update."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            get_document,
            update_document_content,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>Original text</p>",
            source_type="html",
            title="Test Doc",
        )

        new_html = "<p>Updated text</p><p>Second paragraph</p>"
        updated = await update_document_content(
            document_id=doc.id,
            content=new_html,
            workspace_id=workspace.id,
        )

        assert updated.content == new_html

        # Verify persistence via fresh fetch
        refetched = await get_document(doc.id)
        assert refetched is not None
        assert refetched.content == new_html

    @pytest.mark.asyncio
    async def test_rebuilds_paragraph_map(self) -> None:
        """AC3.3: paragraph_map is consistent with updated content."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            update_document_content,
        )
        from promptgrimoire.db.workspaces import create_workspace
        from promptgrimoire.input_pipeline import build_paragraph_map_for_json

        workspace = await create_workspace()
        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>One</p>",
            source_type="html",
            paragraph_map={"0": 1},
        )

        new_html = "<p>First</p><p>Second</p><p>Third</p>"
        updated = await update_document_content(
            document_id=doc.id,
            content=new_html,
            workspace_id=workspace.id,
        )

        expected_map = build_paragraph_map_for_json(new_html, auto_number=True)
        assert updated.paragraph_map == expected_map
        # Should have 3 paragraph entries
        assert len(updated.paragraph_map) == 3

    @pytest.mark.asyncio
    async def test_sets_search_dirty_on_workspace(self) -> None:
        """Parent workspace gets search_dirty=True after content update."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            update_document_content,
        )
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        workspace = await create_workspace()
        # Clear search_dirty first so we can detect the change
        from promptgrimoire.db.workspaces import _update_workspace_fields

        await _update_workspace_fields(workspace.id, search_dirty=False)

        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>Original</p>",
            source_type="html",
        )

        await update_document_content(
            document_id=doc.id,
            content="<p>Changed</p>",
            workspace_id=workspace.id,
        )

        ws = await get_workspace(workspace.id)
        assert ws is not None
        assert ws.search_dirty is True

    @pytest.mark.asyncio
    async def test_raises_on_missing_document(self) -> None:
        """ValueError raised when document does not exist."""
        from uuid import uuid4

        from promptgrimoire.db.workspace_documents import update_document_content
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        with pytest.raises(ValueError, match="not found"):
            await update_document_content(
                document_id=uuid4(),
                content="<p>Nope</p>",
                workspace_id=workspace.id,
            )
