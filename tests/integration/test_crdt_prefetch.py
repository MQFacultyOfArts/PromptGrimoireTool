"""Tests for CRDT pre-fetch kwargs on registry and tag consistency.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Workspace isolation: Each test creates its own workspace via UUID.
"""

from __future__ import annotations

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestRegistryPreFetchedWorkspace:
    """Registry.get_or_create_for_workspace with workspace kwarg."""

    @pytest.mark.asyncio
    async def test_with_prefetched_workspace(self) -> None:
        """Registry uses pre-fetched workspace data when provided."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            AnnotationDocumentRegistry,
        )
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.workspaces import (
            get_workspace,
            save_workspace_crdt_state,
        )

        # Create workspace with CRDT state
        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()
            workspace_id = ws.id

        # Populate CRDT state via the normal path
        seed_doc = AnnotationDocument("seed")
        seed_doc.add_highlight(
            start_char=0, end_char=5, tag="test", text="hello", author="tester"
        )
        await save_workspace_crdt_state(workspace_id, seed_doc.get_full_state())

        # Fetch workspace object (simulates pre-fetch)
        workspace = await get_workspace(workspace_id)
        assert workspace is not None
        assert workspace.crdt_state is not None

        # Call with pre-fetched workspace
        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(
            workspace_id,
            workspace=workspace,
        )

        highlights = doc.get_all_highlights()
        assert len(highlights) == 1
        assert highlights[0]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_without_workspace_kwarg(self) -> None:
        """Registry fetches workspace from DB when kwarg omitted."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            AnnotationDocumentRegistry,
        )
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.workspaces import save_workspace_crdt_state

        # Create workspace with CRDT state
        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()
            workspace_id = ws.id

        seed_doc = AnnotationDocument("seed")
        seed_doc.add_highlight(
            start_char=0, end_char=5, tag="test", text="world", author="tester"
        )
        await save_workspace_crdt_state(workspace_id, seed_doc.get_full_state())

        # Call without workspace kwarg -- should fetch from DB
        registry = AnnotationDocumentRegistry()
        doc = await registry.get_or_create_for_workspace(workspace_id)

        highlights = doc.get_all_highlights()
        assert len(highlights) == 1
        assert highlights[0]["text"] == "world"


class TestTagConsistencyPreFetched:
    """Tests for _ensure_crdt_tag_consistency with pre-fetched tags/tag_groups."""

    @pytest.mark.asyncio
    async def test_with_prefetched_tags(self) -> None:
        """Consistency check uses pre-fetched tags when provided."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            _ensure_crdt_tag_consistency,
        )
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Tag, TagGroup, Workspace
        from promptgrimoire.db.tags import (
            list_tag_groups_for_workspace,
            list_tags_for_workspace,
        )

        # Create workspace with tags in DB
        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()

            group = TagGroup(
                workspace_id=ws.id,
                name="TestGroup",
                color="#00ff00",
                order_index=0,
            )
            session.add(group)
            await session.flush()

            tag = Tag(
                workspace_id=ws.id,
                group_id=group.id,
                name="TestTag",
                color="#ff0000",
                order_index=0,
            )
            session.add(tag)
            await session.flush()

            workspace_id = ws.id

        # Fetch tags from DB (simulates pre-fetch)
        db_tags = await list_tags_for_workspace(workspace_id)
        db_groups = await list_tag_groups_for_workspace(workspace_id)

        # Create empty annotation doc and call with pre-fetched data
        doc = AnnotationDocument(f"ws-{workspace_id}")
        await _ensure_crdt_tag_consistency(
            doc,
            workspace_id,
            tags=db_tags,
            tag_groups=db_groups,
        )

        crdt_tags = doc.list_tags()
        crdt_groups = doc.list_tag_groups()
        assert len(crdt_tags) == 1
        assert len(crdt_groups) == 1

        tag_data = next(iter(crdt_tags.values()))
        assert tag_data["name"] == "TestTag"
        assert tag_data["colour"] == "#ff0000"

        group_data = next(iter(crdt_groups.values()))
        assert group_data["name"] == "TestGroup"

    @pytest.mark.asyncio
    async def test_without_tags_kwarg(self) -> None:
        """Consistency check fetches tags from DB when kwargs omitted."""
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
            _ensure_crdt_tag_consistency,
        )
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Tag, TagGroup, Workspace

        # Create workspace with tags in DB
        async with get_session() as session:
            ws = Workspace()
            session.add(ws)
            await session.flush()

            group = TagGroup(
                workspace_id=ws.id,
                name="BWCompatGroup",
                color="#0000ff",
                order_index=0,
            )
            session.add(group)
            await session.flush()

            tag = Tag(
                workspace_id=ws.id,
                group_id=group.id,
                name="BWCompatTag",
                color="#00ff00",
                order_index=0,
            )
            session.add(tag)
            await session.flush()

            workspace_id = ws.id

        # Call without kwargs -- should fetch from DB internally
        doc = AnnotationDocument(f"ws-{workspace_id}")
        await _ensure_crdt_tag_consistency(doc, workspace_id)

        crdt_tags = doc.list_tags()
        crdt_groups = doc.list_tag_groups()
        assert len(crdt_tags) == 1
        assert len(crdt_groups) == 1

        tag_data = next(iter(crdt_tags.values()))
        assert tag_data["name"] == "BWCompatTag"
        assert tag_data["colour"] == "#00ff00"

        group_data = next(iter(crdt_groups.values()))
        assert group_data["name"] == "BWCompatGroup"
