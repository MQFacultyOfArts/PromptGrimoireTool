"""Integration tests for FTS search via the navigator query.

Tests exercise search_navigator() — the single combined query that
enforces ACL via the nav CTE and runs FTS against visible workspaces.

Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text

from promptgrimoire.config import get_settings
from promptgrimoire.db.engine import get_session

if TYPE_CHECKING:
    from uuid import UUID

    from promptgrimoire.db.navigator import SearchHit

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


# ── Helpers ────────────────────────────────────────────────────────────


async def _create_owned_workspace_with_document(
    content: str,
    *,
    search_text: str | None = None,
    title: str | None = None,
) -> tuple[UUID, UUID]:
    """Create a user + owned workspace + document for FTS testing.

    Returns (user_id, workspace_id).
    """
    from promptgrimoire.db.acl import grant_permission
    from promptgrimoire.db.models import WorkspaceDocument
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.workspaces import create_workspace

    tag = uuid4().hex[:8]
    user = await create_user(
        email=f"fts-{tag}@test.local",
        display_name=f"FTS User {tag}",
    )

    ws = await create_workspace()
    await grant_permission(ws.id, user.id, "owner")

    # Set title if provided
    if title is not None:
        async with get_session() as session:
            await session.execute(
                text("UPDATE workspace SET title = :title WHERE id = :ws_id"),
                {"title": title, "ws_id": str(ws.id)},
            )

    # Create document
    async with get_session() as session:
        doc = WorkspaceDocument(
            workspace_id=ws.id,
            type="source",
            content=content,
            source_type="html",
        )
        session.add(doc)
        await session.flush()

    # Set search_text if provided
    if search_text is not None:
        async with get_session() as session:
            await session.execute(
                text(
                    "UPDATE workspace "
                    "SET search_text = :search_text, search_dirty = false "
                    "WHERE id = :ws_id"
                ),
                {"search_text": search_text, "ws_id": str(ws.id)},
            )

    return user.id, ws.id


async def _search(
    query: str,
    user_id: UUID,
) -> list[SearchHit]:
    """Run search_navigator with minimal params (privileged, no enrollments)."""
    from promptgrimoire.db.navigator import search_navigator

    return await search_navigator(
        query,
        user_id=user_id,
        is_privileged=True,
        enrolled_course_ids=[],
    )


# ── Infrastructure: search_dirty flag ─────────────────────────────────


class TestSearchDirtyOnCRDTSave:
    """Verify save_workspace_crdt_state sets search_dirty."""

    @pytest.mark.asyncio
    async def test_search_dirty_set_on_crdt_save(self) -> None:
        """Saving CRDT state marks workspace as search_dirty."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            save_workspace_crdt_state,
        )

        workspace = await create_workspace()

        doc = AnnotationDocument("dirty-test")
        doc.add_highlight(
            start_char=0,
            end_char=5,
            tag="test",
            text="hello",
            author="tester",
        )
        crdt_bytes = doc.get_full_state()

        result = await save_workspace_crdt_state(workspace.id, crdt_bytes)
        assert result is True

        reloaded = await get_workspace(workspace.id)
        assert reloaded is not None
        assert reloaded.search_dirty is True


# ── HTML stripping ────────────────────────────────────────────────────


class TestFTSHTMLStripping:
    """HTML tags stripped from indexed content."""

    @pytest.mark.asyncio
    async def test_html_stripped_from_document_search(self) -> None:
        """Search matches text inside HTML tags -- tags stripped."""
        user_id, ws_id = await _create_owned_workspace_with_document(
            "<p>The quick <b>brown</b> fox jumps over the lazy dog</p>"
        )

        results = await _search("brown fox", user_id)

        assert len(results) >= 1
        assert any(h.row.workspace_id == ws_id for h in results)


# ── Snippet highlighting ──────────────────────────────────────────────


class TestFTSSnippetHighlighting:
    """ts_headline returns snippet with matched terms."""

    @pytest.mark.asyncio
    async def test_snippet_contains_mark_tags(self) -> None:
        """Returned snippet wraps matched terms in <mark> tags."""
        user_id, _ws_id = await _create_owned_workspace_with_document(
            "<p>Negligence in workplace safety is a critical issue</p>"
        )

        results = await _search("negligence", user_id)

        assert len(results) >= 1
        assert "<mark>" in results[0].snippet
        assert "</mark>" in results[0].snippet


# ── Short query guard ─────────────────────────────────────────────────


class TestFTSShortQueryGuard:
    """Short queries (<3 chars) do not trigger FTS."""

    @pytest.mark.asyncio
    async def test_two_char_query_returns_empty(self) -> None:
        """Query 'ab' (2 chars) returns empty list."""
        from promptgrimoire.db.navigator import search_navigator

        results = await search_navigator(
            "ab",
            user_id=uuid4(),
            is_privileged=True,
            enrolled_course_ids=[],
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_whitespace_only_query_returns_empty(self) -> None:
        """Whitespace-only query returns empty list."""
        from promptgrimoire.db.navigator import search_navigator

        results = await search_navigator(
            "   ",
            user_id=uuid4(),
            is_privileged=True,
            enrolled_course_ids=[],
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self) -> None:
        """Empty string query returns empty list."""
        from promptgrimoire.db.navigator import search_navigator

        results = await search_navigator(
            "",
            user_id=uuid4(),
            is_privileged=True,
            enrolled_course_ids=[],
        )
        assert results == []


# ── Empty content ─────────────────────────────────────────────────────


class TestFTSEmptyContent:
    """Empty document content -- valid (empty) tsvector."""

    @pytest.mark.asyncio
    async def test_empty_content_no_error(self) -> None:
        """Document with empty content: no error, not in results."""
        user_id, ws_id = await _create_owned_workspace_with_document("")

        results = await _search("anything", user_id)
        assert not any(h.row.workspace_id == ws_id for h in results)


# ── Content matches with snippets ─────────────────────────────────────


class TestFTSContentMatches:
    """FTS surfaces content matches with snippet."""

    @pytest.mark.asyncio
    async def test_search_returns_snippet_for_document(self) -> None:
        """Document content match returns result with snippet."""
        user_id, ws_id = await _create_owned_workspace_with_document(
            "<p>The defendant breached their duty of care</p>"
        )

        results = await _search("duty of care", user_id)

        assert len(results) >= 1
        match = next(h for h in results if h.row.workspace_id == ws_id)
        assert match.snippet  # non-empty snippet

    @pytest.mark.asyncio
    async def test_search_crdt_search_text(self) -> None:
        """Search text in CRDT search_text returns result."""
        user_id, ws_id = await _create_owned_workspace_with_document(
            "<p>Unrelated content here</p>",
            search_text="The statute of limitations has expired",
        )

        results = await _search("statute limitations", user_id)

        assert len(results) >= 1
        match = next(h for h in results if h.row.workspace_id == ws_id)
        assert match.snippet


# ── Malformed query ───────────────────────────────────────────────────


class TestFTSMalformedQuery:
    """Malformed query input handled gracefully."""

    @pytest.mark.asyncio
    async def test_malformed_query_no_error(self) -> None:
        """Trailing operator handled by websearch_to_tsquery."""
        user_id, _ws_id = await _create_owned_workspace_with_document(
            "<p>Legal analysis of the workplace injury case</p>"
        )

        # websearch_to_tsquery silently drops the trailing operator
        results = await _search("legal &", user_id)
        assert len(results) >= 1


# ── ACL restricts search results ─────────────────────────────────────


class TestFTSACLRestriction:
    """Search results restricted to workspaces visible via ACL."""

    @pytest.mark.asyncio
    async def test_other_users_workspaces_not_visible(self) -> None:
        """User A cannot see User B's workspace in search results."""
        # User A owns a workspace with "negligence"
        user_a_id, ws_a = await _create_owned_workspace_with_document(
            "<p>Negligence and breach of duty analysis</p>"
        )
        # User B owns a different workspace with "negligence"
        _user_b_id, ws_b = await _create_owned_workspace_with_document(
            "<p>Negligence in product liability cases</p>"
        )

        # Search as User A — should only see ws_a
        results = await _search("negligence", user_a_id)

        ws_ids_in_results = {h.row.workspace_id for h in results}
        assert ws_a in ws_ids_in_results
        assert ws_b not in ws_ids_in_results


# ── Relevance ordering ────────────────────────────────────────────────


class TestFTSRelevanceOrdering:
    """Results ordered by relevance (ts_rank)."""

    @pytest.mark.asyncio
    async def test_more_matches_rank_higher(self) -> None:
        """Document with more matching terms ranks higher."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"rank-{tag}@test.local",
            display_name=f"Rank User {tag}",
        )

        # ws_1 has "negligence" once
        ws_1 = await create_workspace()
        await grant_permission(ws_1.id, user.id, "owner")
        async with get_session() as session:
            from promptgrimoire.db.models import WorkspaceDocument

            session.add(
                WorkspaceDocument(
                    workspace_id=ws_1.id,
                    type="source",
                    content="<p>A case about negligence in the workplace</p>",
                    source_type="html",
                )
            )

        # ws_2 has "negligence" multiple times
        ws_2 = await create_workspace()
        await grant_permission(ws_2.id, user.id, "owner")
        async with get_session() as session:
            session.add(
                WorkspaceDocument(
                    workspace_id=ws_2.id,
                    type="source",
                    content=(
                        "<p>Negligence, contributory negligence, and "
                        "comparative negligence are all forms of "
                        "negligence in tort law</p>"
                    ),
                    source_type="html",
                )
            )

        results = await _search("negligence", user.id)

        assert len(results) >= 2
        ranked_ws_ids = [h.row.workspace_id for h in results]
        idx_1 = ranked_ws_ids.index(ws_1.id)
        idx_2 = ranked_ws_ids.index(ws_2.id)
        assert idx_2 < idx_1, "Workspace with more matches should rank higher"


# ── NULL search_text ──────────────────────────────────────────────────


class TestFTSNullSearchText:
    """Workspace with search_text = NULL handled gracefully."""

    @pytest.mark.asyncio
    async def test_null_search_text_no_error(self) -> None:
        """Workspace with NULL search_text causes no error."""
        user_id, ws_id = await _create_owned_workspace_with_document(
            "<p>Some content here</p>",
            # search_text left as None (default)
        )

        results = await _search("nonexistent term", user_id)
        assert not any(h.row.workspace_id == ws_id for h in results)
