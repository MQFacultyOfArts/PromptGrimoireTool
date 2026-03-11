"""Integration tests for FTS search via the navigator query.

Tests exercise search_navigator() — the single combined query that
enforces ACL via the nav CTE and runs FTS against visible workspaces.

Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

import time
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


async def _create_workspace_with_metadata(
    *,
    owner_display_name: str | None = None,
    activity_title: str = "Test Activity",
    week_title: str = "Week 1",
    course_code: str | None = None,
    course_name: str = "Test Course",
    workspace_title: str | None = None,
    document_content: str = "<p>placeholder content</p>",
) -> tuple[UUID, UUID]:
    """Create a full hierarchy (user/course/week/activity/workspace) for metadata FTS.

    Returns (user_id, workspace_id).
    """
    from promptgrimoire.db.acl import grant_permission
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.models import WorkspaceDocument
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week
    from promptgrimoire.db.workspaces import create_workspace

    tag = uuid4().hex[:8]
    user = await create_user(
        email=f"meta-{tag}@test.local",
        display_name=owner_display_name or f"Meta User {tag}",
    )

    course = await create_course(
        code=course_code or f"M{tag[:6].upper()}",
        name=course_name,
        semester="2026-S1",
    )
    week = await create_week(
        course_id=course.id,
        week_number=1,
        title=week_title,
    )
    activity = await create_activity(
        week_id=week.id,
        title=activity_title,
    )

    # Create the target workspace and place it under the activity/course
    ws = await create_workspace()
    await grant_permission(ws.id, user.id, "owner")

    async with get_session() as session:
        await session.execute(
            text(
                "UPDATE workspace "
                "SET activity_id = :aid, course_id = NULL "
                "WHERE id = :ws_id"
            ),
            {"aid": str(activity.id), "ws_id": str(ws.id)},
        )

    # Set workspace title if provided
    if workspace_title is not None:
        async with get_session() as session:
            await session.execute(
                text("UPDATE workspace SET title = :title WHERE id = :ws_id"),
                {"title": workspace_title, "ws_id": str(ws.id)},
            )

    # Create document
    async with get_session() as session:
        doc = WorkspaceDocument(
            workspace_id=ws.id,
            type="source",
            content=document_content,
            source_type="html",
        )
        session.add(doc)
        await session.flush()

    return user.id, ws.id


async def _search(
    query: str,
    user_id: UUID,
    *,
    is_privileged: bool = False,
    enrolled_course_ids: list[UUID] | None = None,
) -> list[SearchHit]:
    """Run search_navigator with minimal params."""
    from promptgrimoire.db.navigator import search_navigator

    return await search_navigator(
        query,
        user_id=user_id,
        is_privileged=is_privileged,
        enrolled_course_ids=enrolled_course_ids or [],
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

    @pytest.mark.asyncio
    async def test_privileged_sees_unshared_peer_workspace(self) -> None:
        """Privileged user sees peer workspace even if not shared_with_class."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.models import WorkspaceDocument
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        instructor = await create_user(
            email=f"instr-{tag}@test.local",
            display_name=f"Instructor {tag}",
        )
        student = await create_user(
            email=f"stud-{tag}@test.local",
            display_name=f"Student {tag}",
        )

        course = await create_course(
            code=f"C{tag}",
            name=f"Course {tag}",
            semester="2026-S1",
        )
        course_id = course.id
        await enroll_user(course_id, instructor.id, role="student")
        await enroll_user(course_id, student.id, role="student")

        # Student workspace with searchable content, NOT shared
        ws = await create_workspace()
        await grant_permission(ws.id, student.id, "owner")
        # Place workspace in the course
        async with get_session() as session:
            await session.execute(
                text("UPDATE workspace SET course_id = :cid WHERE id = :ws_id"),
                {"cid": course_id, "ws_id": ws.id},
            )
        async with get_session() as session:
            session.add(
                WorkspaceDocument(
                    workspace_id=ws.id,
                    type="source",
                    content="<p>Tortfeasor liability analysis</p>",
                    source_type="html",
                )
            )

        # Non-privileged instructor: should NOT see unshared workspace
        results = await _search(
            "tortfeasor",
            instructor.id,
            enrolled_course_ids=[course_id],
        )
        assert not any(h.row.workspace_id == ws.id for h in results)

        # Privileged instructor: SHOULD see all peer workspaces
        results = await _search(
            "tortfeasor",
            instructor.id,
            is_privileged=True,
            enrolled_course_ids=[course_id],
        )
        assert any(h.row.workspace_id == ws.id for h in results)


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


# ── Metadata search ──────────────────────────────────────────────────


class TestMetadataSearchOwnerName:
    """AC1.1: Search matches owner display name."""

    @pytest.mark.asyncio
    async def test_search_by_owner_display_name(self) -> None:
        """Searching owner name surfaces the workspace."""
        user_id, ws_id = await _create_workspace_with_metadata(
            owner_display_name="Bartholomew Greenfield",
        )

        results = await _search("Bartholomew", user_id)

        assert len(results) >= 1
        assert any(h.row.workspace_id == ws_id for h in results)


class TestMetadataSearchActivityTitle:
    """AC2.1: Search matches activity title."""

    @pytest.mark.asyncio
    async def test_search_by_activity_title(self) -> None:
        """Searching activity title surfaces the workspace."""
        user_id, ws_id = await _create_workspace_with_metadata(
            activity_title="Contractual Obligations Analysis",
        )

        results = await _search("Contractual Obligations", user_id)

        assert len(results) >= 1
        assert any(h.row.workspace_id == ws_id for h in results)


class TestMetadataSearchWeekTitle:
    """AC3.1: Search matches week title."""

    @pytest.mark.asyncio
    async def test_search_by_week_title(self) -> None:
        """Searching week title surfaces the workspace."""
        user_id, ws_id = await _create_workspace_with_metadata(
            week_title="Foundations of Tort",
        )

        results = await _search("Foundations Tort", user_id)

        assert len(results) >= 1
        assert any(h.row.workspace_id == ws_id for h in results)


class TestMetadataSearchCourseCode:
    """AC4.1: Search matches course code."""

    @pytest.mark.asyncio
    async def test_search_by_course_code(self) -> None:
        """Searching course code surfaces the workspace."""
        user_id, ws_id = await _create_workspace_with_metadata(
            course_code="LAWS3100",
        )

        results = await _search("LAWS3100", user_id)

        assert len(results) >= 1
        assert any(h.row.workspace_id == ws_id for h in results)


class TestMetadataSearchCourseName:
    """AC5.1: Search matches course name."""

    @pytest.mark.asyncio
    async def test_search_by_course_name(self) -> None:
        """Searching course name surfaces the workspace."""
        user_id, ws_id = await _create_workspace_with_metadata(
            course_name="Environmental Regulation",
        )

        results = await _search("Environmental Regulation", user_id)

        assert len(results) >= 1
        assert any(h.row.workspace_id == ws_id for h in results)


class TestMetadataSearchWorkspaceTitle:
    """Search matches workspace title via metadata leg."""

    @pytest.mark.asyncio
    async def test_search_by_workspace_title(self) -> None:
        """Searching workspace title surfaces the workspace."""
        user_id, ws_id = await _create_workspace_with_metadata(
            workspace_title="Jurisprudential Analysis Portfolio",
        )

        results = await _search("Jurisprudential Analysis", user_id)

        assert len(results) >= 1
        assert any(h.row.workspace_id == ws_id for h in results)


class TestMetadataSearchSnippetHighlight:
    """AC6.1: Metadata match snippet contains <mark> tags."""

    @pytest.mark.asyncio
    async def test_metadata_snippet_has_mark_tags(self) -> None:
        """Metadata hit snippet wraps matched terms in <mark> tags."""
        user_id, ws_id = await _create_workspace_with_metadata(
            course_code="LAWS3100",
            course_name="Environmental Regulation",
        )

        results = await _search("LAWS3100", user_id)

        assert len(results) >= 1
        hit = next(h for h in results if h.row.workspace_id == ws_id)
        assert "<mark>" in hit.snippet
        assert "</mark>" in hit.snippet


class TestMetadataSearchOrphanWorkspace:
    """AC9.1: Orphan workspace (no activity/week/course) still searchable."""

    @pytest.mark.asyncio
    async def test_orphan_workspace_found_by_title(self) -> None:
        """Workspace with no activity still appears in search by title."""
        tag = uuid4().hex[:8]
        title = f"Orphan Jurisprudence {tag}"
        user_id, ws_id = await _create_owned_workspace_with_document(
            "<p>placeholder</p>",
            title=title,
        )

        results = await _search(f"Orphan Jurisprudence {tag}", user_id)

        assert len(results) >= 1
        assert any(h.row.workspace_id == ws_id for h in results)


class TestMetadataSearchRegressionDocumentContent:
    """AC7.1: Document content search still works alongside metadata."""

    @pytest.mark.asyncio
    async def test_document_content_still_searchable(self) -> None:
        """Document content match still surfaces workspace."""
        user_id, ws_id = await _create_workspace_with_metadata(
            document_content="<p>promissory estoppel in contract law</p>",
        )

        results = await _search("promissory estoppel", user_id)

        assert len(results) >= 1
        assert any(h.row.workspace_id == ws_id for h in results)


class TestMetadataSearchRegressionCRDTSearchText:
    """AC7.2: CRDT search_text search still works alongside metadata."""

    @pytest.mark.asyncio
    async def test_crdt_search_text_still_searchable(self) -> None:
        """CRDT search_text match still surfaces workspace."""
        user_id, ws_id = await _create_owned_workspace_with_document(
            "<p>Unrelated content here</p>",
            search_text="quantum meruit restitution",
        )

        results = await _search("quantum meruit", user_id)

        assert len(results) >= 1
        assert any(h.row.workspace_id == ws_id for h in results)


# ── Performance at scale ─────────────────────────────────────────────


class TestMetadataSearchPerformance:
    """Metadata search latency at 1k-workspace scale."""

    @pytest.mark.asyncio
    async def test_metadata_search_latency_at_scale(self) -> None:
        """Metadata search across 1k+ visible workspaces completes in <2s."""
        # Count workspaces to guard against missing load data
        async with get_session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM workspace"))
            ws_count = result.scalar_one()

        if ws_count < 1000:
            pytest.skip(
                f"Only {ws_count} workspaces — run `uv run grimoire loadtest` first"
            )

        # Find a privileged user from load data (instructor)
        async with get_session() as session:
            result = await session.execute(
                text("""
                    SELECT u.id FROM "user" u
                    JOIN course_enrollment ce ON ce.user_id = u.id
                    JOIN course_role cr ON cr.name = ce.role
                    WHERE cr.is_staff = true
                    LIMIT 1
                """)
            )
            row = result.one_or_none()
            if row is None:
                pytest.skip("No staff user found in load data")
            instructor_id = row[0]

        # Get enrolled course IDs for this instructor
        async with get_session() as session:
            result = await session.execute(
                text("""
                    SELECT ce.course_id FROM course_enrollment ce
                    WHERE ce.user_id = :uid
                """),
                {"uid": instructor_id},
            )
            enrolled_ids = [r[0] for r in result.all()]

        # Measure metadata search latency
        start = time.monotonic()
        results = await _search(
            "LAWS",  # Common prefix in seeded course codes
            instructor_id,
            is_privileged=True,
            enrolled_course_ids=enrolled_ids,
        )
        elapsed = time.monotonic() - start

        assert len(results) > 0, "Expected metadata search to return results"
        assert elapsed < 2.0, (
            f"Metadata search took {elapsed:.2f}s (threshold: 2.0s) "
            f"across {ws_count} workspaces"
        )
