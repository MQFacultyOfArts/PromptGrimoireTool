"""Tests for list_document_headers() deferred content loading.

Verifies that list_document_headers() returns document metadata without
transferring the content column, while list_documents() still returns
full content for export paths.

Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm.exc import DetachedInstanceError

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestListDocumentHeaders:
    """Tests for list_document_headers() with deferred content."""

    @pytest.mark.asyncio
    async def test_returns_metadata_fields(self) -> None:
        """AC1.1: Headers contain all metadata columns populated."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            list_document_headers,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>Test content for headers</p>",
            source_type="html",
            title="Test Doc",
            auto_number_paragraphs=False,
        )

        headers = await list_document_headers(workspace.id)

        assert len(headers) == 1
        doc = headers[0]
        # All metadata fields are accessible
        assert doc.id is not None
        assert doc.workspace_id == workspace.id
        assert doc.title == "Test Doc"
        assert doc.order_index == 0
        assert doc.type == "source"
        assert doc.source_type == "html"
        assert doc.auto_number_paragraphs is False
        assert doc.created_at is not None

    @pytest.mark.asyncio
    async def test_content_access_raises_detached_instance_error(self) -> None:
        """AC1.3: .content on headers-only raises DetachedInstanceError."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            list_document_headers,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>This content should not be loaded</p>",
            source_type="html",
        )

        headers = await list_document_headers(workspace.id)

        assert len(headers) == 1
        with pytest.raises(DetachedInstanceError):
            _ = headers[0].content

    @pytest.mark.asyncio
    async def test_ordering_by_order_index(self) -> None:
        """Headers are returned ordered by order_index."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            list_document_headers,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        doc1 = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>First</p>",
            source_type="html",
            title="First",
        )
        doc2 = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>Second</p>",
            source_type="html",
            title="Second",
        )

        headers = await list_document_headers(workspace.id)

        assert len(headers) == 2
        assert headers[0].id == doc1.id
        assert headers[1].id == doc2.id

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_empty_list(self) -> None:
        """Headers query on workspace with no documents returns empty list."""
        from promptgrimoire.db.workspace_documents import list_document_headers
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        headers = await list_document_headers(workspace.id)

        assert headers == []


class TestListDocumentsFullContent:
    """Verify list_documents() still returns full content (AC1.4)."""

    @pytest.mark.asyncio
    async def test_content_accessible_on_full_documents(self) -> None:
        """AC1.4: list_documents() returns content for export paths."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            list_documents,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        expected_content = "<p>Full content for export</p>"
        await add_document(
            workspace_id=workspace.id,
            type="source",
            content=expected_content,
            source_type="html",
        )

        docs = await list_documents(workspace.id)

        assert len(docs) == 1
        assert docs[0].content == expected_content
