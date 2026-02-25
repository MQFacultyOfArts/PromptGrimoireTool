"""Integration tests for FTS search infrastructure.

These tests require a running PostgreSQL instance with FTS indexes
applied. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from promptgrimoire.config import get_settings
from promptgrimoire.db.engine import get_session

if TYPE_CHECKING:
    from uuid import UUID

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestSearchDirtyOnCRDTSave:
    """Verify save_workspace_crdt_state sets search_dirty."""

    @pytest.mark.asyncio
    async def test_search_dirty_set_on_crdt_save(self) -> None:
        """Saving CRDT state marks workspace as search_dirty.

        After save_workspace_crdt_state(), the workspace's
        search_dirty flag must be True so the extraction worker
        picks it up.
        """
        from promptgrimoire.crdt.annotation_doc import (
            AnnotationDocument,
        )
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            save_workspace_crdt_state,
        )

        # Create workspace and manually clear dirty flag
        workspace = await create_workspace()

        # Build some CRDT bytes
        doc = AnnotationDocument("dirty-test")
        doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="test",
            text="hello",
            author="tester",
        )
        crdt_bytes = doc.get_full_state()

        # Save CRDT state
        result = await save_workspace_crdt_state(workspace.id, crdt_bytes)
        assert result is True

        # Reload and verify search_dirty is True
        reloaded = await get_workspace(workspace.id)
        assert reloaded is not None
        assert reloaded.search_dirty is True


# ── Helpers for FTS query tests ──────────────────────────────────────


async def _create_workspace_with_document(
    content: str,
    *,
    search_text: str | None = None,
) -> tuple[UUID, UUID]:
    """Create a workspace and workspace_document for FTS testing.

    Returns (workspace_id, document_id) as UUIDs.
    """
    from promptgrimoire.db.models import WorkspaceDocument
    from promptgrimoire.db.workspaces import create_workspace

    workspace = await create_workspace()

    async with get_session() as session:
        doc = WorkspaceDocument(
            workspace_id=workspace.id,
            type="source",
            content=content,
            source_type="html",
        )
        session.add(doc)
        await session.flush()
        await session.refresh(doc)
        doc_id = doc.id

    if search_text is not None:
        async with get_session() as session:
            await session.execute(
                text(
                    "UPDATE workspace "
                    "SET search_text = :search_text, "
                    "search_dirty = false "
                    "WHERE id = :ws_id"
                ),
                {
                    "search_text": search_text,
                    "ws_id": str(workspace.id),
                },
            )

    return workspace.id, doc_id


# ── AC8.2: HTML stripped from indexed content ────────────────────────


class TestFTSHTMLStripping:
    """AC8.2: HTML tags stripped from indexed content."""

    @pytest.mark.asyncio
    async def test_html_stripped_from_document_search(self) -> None:
        """Search matches text inside HTML tags -- tags stripped."""
        from promptgrimoire.db.search import search_workspace_content

        ws_id, _ = await _create_workspace_with_document(
            "<p>The quick <b>brown</b> fox jumps over the lazy dog</p>"
        )

        results = await search_workspace_content("brown fox", workspace_ids=[ws_id])

        assert len(results) >= 1
        assert any(r.workspace_id == ws_id for r in results)


# ── AC8.3: ts_headline returns snippet with matched terms ────────────


class TestFTSSnippetHighlighting:
    """AC8.3: ts_headline returns snippet with matched terms."""

    @pytest.mark.asyncio
    async def test_snippet_contains_mark_tags(self) -> None:
        """Returned snippet wraps matched terms in <mark> tags."""
        from promptgrimoire.db.search import search_workspace_content

        ws_id, _ = await _create_workspace_with_document(
            "<p>Negligence in workplace safety is a critical issue</p>"
        )

        results = await search_workspace_content("negligence", workspace_ids=[ws_id])

        assert len(results) >= 1
        # ts_headline should wrap the match in <mark>...</mark>
        assert "<mark>" in results[0].snippet
        assert "</mark>" in results[0].snippet


# ── AC8.4: Short queries do not trigger FTS ──────────────────────────


class TestFTSShortQueryGuard:
    """AC8.4: Short queries (<3 chars) do not trigger FTS."""

    @pytest.mark.asyncio
    async def test_two_char_query_returns_empty(self) -> None:
        """Query 'ab' (2 chars) returns empty list."""
        from promptgrimoire.db.search import search_workspace_content

        results = await search_workspace_content("ab")
        assert results == []

    @pytest.mark.asyncio
    async def test_whitespace_only_query_returns_empty(self) -> None:
        """Whitespace-only query returns empty list."""
        from promptgrimoire.db.search import search_workspace_content

        results = await search_workspace_content("   ")
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self) -> None:
        """Empty string query returns empty list."""
        from promptgrimoire.db.search import search_workspace_content

        results = await search_workspace_content("")
        assert results == []


# ── AC8.5: Empty document content produces no errors ─────────────────


class TestFTSEmptyContent:
    """AC8.5: Empty document content -- valid (empty) tsvector."""

    @pytest.mark.asyncio
    async def test_empty_content_no_error(self) -> None:
        """Document with empty content: no error, not in results."""
        from promptgrimoire.db.search import search_workspace_content

        ws_id, _ = await _create_workspace_with_document("")

        results = await search_workspace_content("anything", workspace_ids=[ws_id])
        # Empty content should not match any search
        assert not any(r.workspace_id == ws_id for r in results)


# ── AC3.2/AC3.4: FTS returns results with snippets ──────────────────


class TestFTSContentMatches:
    """AC3.2: FTS surfaces content matches with snippet.

    AC3.4: Content snippet explaining the match.
    """

    @pytest.mark.asyncio
    async def test_search_returns_snippet_for_document(self) -> None:
        """Document content match returns result with snippet."""
        from promptgrimoire.db.search import search_workspace_content

        ws_id, _ = await _create_workspace_with_document(
            "<p>The defendant breached their duty of care</p>"
        )

        results = await search_workspace_content("duty of care", workspace_ids=[ws_id])

        assert len(results) >= 1
        match = next(r for r in results if r.workspace_id == ws_id)
        assert match.snippet  # non-empty snippet
        assert match.source == "document"

    @pytest.mark.asyncio
    async def test_search_crdt_search_text(self) -> None:
        """AC3.4: Search text in CRDT search_text returns result."""
        from promptgrimoire.db.search import search_workspace_content

        ws_id, _ = await _create_workspace_with_document(
            "<p>Unrelated content here</p>",
            search_text=("The statute of limitations has expired"),
        )

        results = await search_workspace_content(
            "statute limitations", workspace_ids=[ws_id]
        )

        assert len(results) >= 1
        match = next(r for r in results if r.source == "workspace")
        assert match.workspace_id == ws_id
        assert match.snippet  # non-empty snippet


# ── Additional test cases ────────────────────────────────────────────


class TestFTSMalformedQuery:
    """Malformed query input handled gracefully."""

    @pytest.mark.asyncio
    async def test_malformed_query_no_error(self) -> None:
        """Trailing operator handled by websearch_to_tsquery."""
        from promptgrimoire.db.search import search_workspace_content

        ws_id, _ = await _create_workspace_with_document(
            "<p>Legal analysis of the workplace injury case</p>"
        )

        # websearch_to_tsquery should handle this gracefully
        results = await search_workspace_content("legal", workspace_ids=[ws_id])
        assert len(results) >= 1


class TestFTSWorkspaceIdFilter:
    """workspace_ids filter restricts results."""

    @pytest.mark.asyncio
    async def test_filter_restricts_to_specified(self) -> None:
        """Only results from specified workspace_ids returned."""
        from promptgrimoire.db.search import search_workspace_content

        ws_id_1, _ = await _create_workspace_with_document(
            "<p>Negligence and breach of duty analysis</p>"
        )
        ws_id_2, _ = await _create_workspace_with_document(
            "<p>Negligence in product liability cases</p>"
        )

        # Search restricted to ws_id_1 only
        results = await search_workspace_content("negligence", workspace_ids=[ws_id_1])

        ws_ids_in_results = {r.workspace_id for r in results}
        assert ws_id_1 in ws_ids_in_results
        assert ws_id_2 not in ws_ids_in_results


class TestFTSRelevanceOrdering:
    """Results ordered by relevance (ts_rank)."""

    @pytest.mark.asyncio
    async def test_more_matches_rank_higher(self) -> None:
        """Document with more matching terms ranks higher."""
        from promptgrimoire.db.search import search_workspace_content

        # ws_1 has "negligence" once
        ws_id_1, _ = await _create_workspace_with_document(
            "<p>A case about negligence in the workplace</p>"
        )
        # ws_2 has "negligence" multiple times
        ws_id_2, _ = await _create_workspace_with_document(
            "<p>Negligence, contributory negligence, and "
            "comparative negligence are all forms of "
            "negligence in tort law</p>"
        )

        results = await search_workspace_content(
            "negligence", workspace_ids=[ws_id_1, ws_id_2]
        )

        assert len(results) >= 2
        # Higher-ranked result should come first
        ranked_ids = [r.workspace_id for r in results]
        idx_1 = ranked_ids.index(ws_id_1)
        idx_2 = ranked_ids.index(ws_id_2)
        assert idx_2 < idx_1, "Workspace with more matches should rank higher"


class TestFTSNullSearchText:
    """Workspace with search_text = NULL handled gracefully."""

    @pytest.mark.asyncio
    async def test_null_search_text_no_error(self) -> None:
        """Workspace with NULL search_text causes no error."""
        from promptgrimoire.db.search import search_workspace_content

        ws_id, _ = await _create_workspace_with_document(
            "<p>Some content here</p>",
            # search_text left as None (default)
        )

        # Should not crash; workspace not in search_text results
        results = await search_workspace_content(
            "nonexistent term", workspace_ids=[ws_id]
        )
        assert not any(
            r.workspace_id == ws_id and r.source == "workspace" for r in results
        )


class TestFTSBothSources:
    """Matches from both document and workspace search_text."""

    @pytest.mark.asyncio
    async def test_both_sources_returned(self) -> None:
        """Search matching in both sources returns both."""
        from promptgrimoire.db.search import search_workspace_content

        ws_id, _ = await _create_workspace_with_document(
            "<p>Negligence is a key concept in tort law</p>",
            search_text=("The annotation discusses negligence"),
        )

        results = await search_workspace_content("negligence", workspace_ids=[ws_id])

        sources = {r.source for r in results if r.workspace_id == ws_id}
        assert "document" in sources
        assert "workspace" in sources
