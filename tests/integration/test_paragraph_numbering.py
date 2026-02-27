"""Integration tests for paragraph numbering model columns."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlmodel import select

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import Workspace, WorkspaceDocument

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestWorkspaceDocumentParagraphFields:
    """Verify paragraph numbering columns round-trip through the database."""

    @pytest.mark.asyncio
    async def test_defaults_on_new_document(self, db_session: AsyncSession) -> None:
        """New doc gets auto_number_paragraphs=True and empty paragraph_map."""
        # Create a workspace (FK requirement)
        ws = Workspace()
        db_session.add(ws)
        await db_session.flush()

        # Create a document with only required fields (no paragraph args)
        doc = WorkspaceDocument(
            workspace_id=ws.id,
            type="source",
            content="<p><span>Hello</span></p>",
            source_type="text",
        )
        db_session.add(doc)
        await db_session.commit()

        # Reload in a fresh query to exercise the full DB round-trip
        result = await db_session.execute(
            select(WorkspaceDocument).where(WorkspaceDocument.id == doc.id)
        )
        reloaded = result.scalar_one()

        assert reloaded.auto_number_paragraphs is True
        assert reloaded.paragraph_map == {}

    @pytest.mark.asyncio
    async def test_paragraph_map_round_trip(self, db_session: AsyncSession) -> None:
        """paragraph_map survives JSON round-trip with string keys."""
        ws = Workspace()
        db_session.add(ws)
        await db_session.flush()

        test_map: dict[str, int] = {"0": 1, "50": 2, "120": 3}
        doc = WorkspaceDocument(
            workspace_id=ws.id,
            type="source",
            content="<p><span>Test</span></p>",
            source_type="text",
            paragraph_map=test_map,
        )
        db_session.add(doc)
        await db_session.commit()

        # Reload in a fresh query to ensure round-trip through DB
        result = await db_session.execute(
            select(WorkspaceDocument).where(WorkspaceDocument.id == doc.id)
        )
        reloaded = result.scalar_one()

        assert reloaded.paragraph_map == {"0": 1, "50": 2, "120": 3}
        assert all(isinstance(k, str) for k in reloaded.paragraph_map)
        assert all(isinstance(v, int) for v in reloaded.paragraph_map.values())

    @pytest.mark.asyncio
    async def test_source_number_mode(self, db_session: AsyncSession) -> None:
        """auto_number_paragraphs=False persists correctly."""
        ws = Workspace()
        db_session.add(ws)
        await db_session.flush()

        doc = WorkspaceDocument(
            workspace_id=ws.id,
            type="source",
            content="<p><span>AustLII doc</span></p>",
            source_type="html",
            auto_number_paragraphs=False,
        )
        db_session.add(doc)
        await db_session.commit()

        # Reload in a fresh query
        result = await db_session.execute(
            select(WorkspaceDocument).where(WorkspaceDocument.id == doc.id)
        )
        reloaded = result.scalar_one()

        assert reloaded.auto_number_paragraphs is False
