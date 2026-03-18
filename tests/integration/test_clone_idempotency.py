"""Integration tests for #364: clone idempotency.

These tests verify that clone_workspace_from_activity is idempotent --
calling it twice for the same (activity_id, user_id) returns the same
workspace rather than creating duplicates.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _setup_activity():
    """Create a minimal Course -> Week -> Activity with one template document."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week
    from promptgrimoire.db.workspace_documents import add_document

    code = f"C{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="Idempotency Test", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Test Activity")
    await add_document(
        workspace_id=activity.template_workspace_id,
        type="source",
        content="<p>Template content</p>",
        source_type="html",
        title="Template Doc",
    )
    tag = uuid4().hex[:8]
    user = await create_user(
        email=f"idem-{tag}@test.local",
        display_name=f"Idempotency Tester {tag}",
    )
    return activity, user


class TestSequentialIdempotency:
    """Sequential double-clone returns the same workspace.

    Calling clone_workspace_from_activity twice for the same (activity, user)
    must return the same workspace ID. The first call returns a non-empty
    doc_id_map; the second returns an empty map.
    """

    @pytest.mark.asyncio
    async def test_same_workspace_returned(self) -> None:
        """Two sequential clones return the same workspace ID (AC1.1)."""
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        activity, user = await _setup_activity()

        clone1, _ = await clone_workspace_from_activity(activity.id, user.id)
        clone2, _ = await clone_workspace_from_activity(activity.id, user.id)

        assert clone1.id == clone2.id

    @pytest.mark.asyncio
    async def test_first_call_returns_doc_id_map(self) -> None:
        """First clone returns a non-empty doc_id_map (AC5.1)."""
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        activity, user = await _setup_activity()

        _, doc_id_map = await clone_workspace_from_activity(activity.id, user.id)

        assert doc_id_map, "First clone must return a non-empty doc_id_map"

    @pytest.mark.asyncio
    async def test_second_call_returns_empty_doc_id_map(self) -> None:
        """Second clone returns an empty doc_id_map (AC5.2)."""
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        activity, user = await _setup_activity()

        await clone_workspace_from_activity(activity.id, user.id)
        _, doc_id_map = await clone_workspace_from_activity(activity.id, user.id)

        assert doc_id_map == {}


class TestConcurrentIdempotency:
    """Concurrent double-clone returns the same workspace.

    asyncio.gather simulates the double-click scenario. Both calls must
    resolve to the same workspace, with exactly one returning a non-empty
    doc_id_map (the creator) and the other returning an empty map.
    """

    @pytest.mark.asyncio
    async def test_concurrent_clones_return_same_workspace(self) -> None:
        """Two concurrent clones return the same workspace ID (AC2.1)."""
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        activity, user = await _setup_activity()

        results = await asyncio.gather(
            clone_workspace_from_activity(activity.id, user.id),
            clone_workspace_from_activity(activity.id, user.id),
        )

        ws1, _ = results[0]
        ws2, _ = results[1]

        assert ws1.id == ws2.id

    @pytest.mark.asyncio
    async def test_exactly_one_creator_one_idempotent(self) -> None:
        """One result has non-empty doc_id_map, the other has empty."""
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        activity, user = await _setup_activity()

        results = await asyncio.gather(
            clone_workspace_from_activity(activity.id, user.id),
            clone_workspace_from_activity(activity.id, user.id),
        )

        maps = [doc_map for _, doc_map in results]
        non_empty = [m for m in maps if m]
        empty = [m for m in maps if not m]

        assert len(non_empty) == 1, (
            f"Expected exactly one creator, got {len(non_empty)}"
        )
        assert len(empty) == 1, f"Expected exactly one idempotent hit, got {len(empty)}"


class TestFreshCloneReturnContract:
    """A fresh clone returns a complete doc_id_map.

    The doc_id_map must have one entry per template document, with template
    doc IDs as keys and distinct cloned doc IDs as values.
    """

    @pytest.mark.asyncio
    async def test_doc_id_map_covers_all_template_docs(self) -> None:
        """doc_id_map has same length as template documents."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import WorkspaceDocument
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        activity, user = await _setup_activity()

        async with get_session() as session:
            result = await session.exec(
                select(WorkspaceDocument.id).where(
                    WorkspaceDocument.workspace_id == activity.template_workspace_id
                )
            )
            template_doc_ids = set(result.all())

        _, doc_id_map = await clone_workspace_from_activity(activity.id, user.id)

        assert len(doc_id_map) == len(template_doc_ids)

    @pytest.mark.asyncio
    async def test_all_template_doc_ids_are_keys(self) -> None:
        """All template document IDs appear as keys in doc_id_map."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import WorkspaceDocument
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        activity, user = await _setup_activity()

        async with get_session() as session:
            result = await session.exec(
                select(WorkspaceDocument.id).where(
                    WorkspaceDocument.workspace_id == activity.template_workspace_id
                )
            )
            template_doc_ids = set(result.all())

        _, doc_id_map = await clone_workspace_from_activity(activity.id, user.id)

        assert set(doc_id_map.keys()) == template_doc_ids

    @pytest.mark.asyncio
    async def test_cloned_doc_ids_are_distinct_from_template(self) -> None:
        """All cloned doc IDs are distinct from template doc IDs."""
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import WorkspaceDocument
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        activity, user = await _setup_activity()

        async with get_session() as session:
            result = await session.exec(
                select(WorkspaceDocument.id).where(
                    WorkspaceDocument.workspace_id == activity.template_workspace_id
                )
            )
            template_doc_ids = set(result.all())

        _, doc_id_map = await clone_workspace_from_activity(activity.id, user.id)

        cloned_ids = set(doc_id_map.values())
        assert cloned_ids.isdisjoint(template_doc_ids), (
            "Cloned doc IDs must not overlap with template doc IDs"
        )


async def _setup_activity_with_entities(n_docs: int, n_groups: int, n_tags: int):
    """Create activity with a template containing specified entity counts."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.tags import create_tag, create_tag_group
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week
    from promptgrimoire.db.workspace_documents import add_document

    code = f"C{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="Count Test", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Count Activity")

    ws_id = activity.template_workspace_id
    for i in range(n_docs):
        await add_document(
            workspace_id=ws_id,
            type="source",
            content=f"<p>Document {i}</p>",
            source_type="html",
            title=f"Doc {i}",
        )

    for i in range(n_groups):
        await create_tag_group(workspace_id=ws_id, name=f"Group {i}")

    for i in range(n_tags):
        await create_tag(
            workspace_id=ws_id,
            name=f"Tag {i}",
            color=f"#{i:06x}",
        )

    tag = uuid4().hex[:8]
    user = await create_user(
        email=f"count-{tag}@test.local",
        display_name=f"Count Tester {tag}",
    )
    return activity, user


class TestConstantRoundTripCount:
    """AC4.1: Round-trip count is constant regardless of template size."""

    @pytest.mark.asyncio
    async def test_statement_count_is_constant(self) -> None:
        from sqlalchemy import event

        from promptgrimoire.db.engine import _state
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        # Setup small and large templates (this initialises the engine)
        small_activity, small_user = await _setup_activity_with_entities(1, 1, 1)
        large_activity, large_user = await _setup_activity_with_entities(5, 3, 10)

        assert _state.engine is not None, "Engine not initialised after setup"
        sync_engine = _state.engine.sync_engine

        # Count statements for small clone
        small_counter: list[int] = []

        def count_small(*_args: object) -> None:
            small_counter.append(1)

        event.listen(sync_engine, "before_cursor_execute", count_small)
        await clone_workspace_from_activity(small_activity.id, small_user.id)
        event.remove(sync_engine, "before_cursor_execute", count_small)

        # Count statements for large clone
        large_counter: list[int] = []

        def count_large(*_args: object) -> None:
            large_counter.append(1)

        event.listen(sync_engine, "before_cursor_execute", count_large)
        await clone_workspace_from_activity(large_activity.id, large_user.id)
        event.remove(sync_engine, "before_cursor_execute", count_large)

        # O(1) proof: same statement count regardless of template size
        assert len(small_counter) == len(large_counter), (
            f"Statement count should be constant: "
            f"small={len(small_counter)}, large={len(large_counter)}"
        )
