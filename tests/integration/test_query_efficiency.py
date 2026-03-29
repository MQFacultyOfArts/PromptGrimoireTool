"""Query efficiency regression tests.

Prevents reintroduction of redundant queries by measuring SQL statement
counts for key operations. Uses SQLAlchemy engine event instrumentation.

Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Engine

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


@contextmanager
def count_queries(engine: Engine) -> Iterator[list[int]]:
    """Count SQL statements executed against *engine*.

    Yields a list that accumulates one element per statement.
    Use ``len(counter)`` after the block to get the count.

    The listener is removed on exit even if an exception occurs.
    """
    from sqlalchemy import event

    counter: list[int] = []

    def _on_execute(*_args: object) -> None:
        counter.append(1)

    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)


class TestDocumentHeadersEfficiency:
    """Verify list_document_headers() query efficiency."""

    @pytest.mark.asyncio
    async def test_headers_exclude_content(self) -> None:
        """AC1.1, AC1.3: metadata present, .content deferred."""
        from sqlalchemy.orm.exc import DetachedInstanceError

        from promptgrimoire.db.workspace_documents import (
            add_document,
            list_document_headers,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        for i in range(3):
            await add_document(
                workspace_id=workspace.id,
                type="source",
                content=f"<p>Content {i}</p>",
                source_type="html",
                title=f"Doc {i}",
            )

        headers = await list_document_headers(workspace.id)

        assert len(headers) == 3
        # All metadata accessible
        for doc in headers:
            assert doc.id is not None
            assert doc.workspace_id == workspace.id
            assert doc.title is not None
            assert doc.order_index is not None
        # Content NOT loaded
        with pytest.raises(DetachedInstanceError):
            _ = headers[0].content

    @pytest.mark.asyncio
    async def test_page_load_document_query_count(self) -> None:
        """AC1.1: list_document_headers() executes exactly 1 SELECT."""
        from promptgrimoire.db.engine import _state
        from promptgrimoire.db.workspace_documents import (
            add_document,
            list_document_headers,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        for i in range(3):
            await add_document(
                workspace_id=workspace.id,
                type="source",
                content=f"<p>Content {i}</p>",
                source_type="html",
                title=f"Doc {i}",
            )

        assert _state.engine is not None, "Engine not initialised"
        sync_engine = _state.engine.sync_engine

        with count_queries(sync_engine) as counter:
            await list_document_headers(workspace.id)

        assert len(counter) == 1, (
            f"list_document_headers() should execute 1 query, got {len(counter)}"
        )


class TestPlacementQueryEfficiency:
    """Verify placement context query efficiency after JOIN optimisation."""

    @pytest.mark.asyncio
    async def test_placement_context_query_count(self) -> None:
        """Placement context for activity workspace: ≤2 queries.

        get_placement_context() fetches workspace + template EXISTS in one
        query, then resolves Activity -> Week -> Course via a single JOIN.
        """
        from uuid import uuid4

        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.engine import _state
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            get_placement_context,
        )

        code = f"C{uuid4().hex[:6].upper()}"
        course = await create_course(
            code=code,
            name="Efficiency Test",
            semester="2026-S1",
        )
        week = await create_week(
            course_id=course.id,
            week_number=1,
            title="W1",
        )
        activity = await create_activity(
            week_id=week.id,
            title="A1",
        )
        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"eff-{tag}@test.local",
            display_name=f"Efficiency Tester {tag}",
        )
        ws, _id_map = await clone_workspace_from_activity(
            activity.id,
            user.id,
        )

        assert _state.engine is not None
        sync_engine = _state.engine.sync_engine

        with count_queries(sync_engine) as counter:
            await get_placement_context(ws.id)

        # workspace + template EXISTS (1) + Activity-Week-Course JOIN (1) = 2
        assert len(counter) <= 2, (
            f"get_placement_context() should need ≤2 queries, got {len(counter)}"
        )

    @pytest.mark.asyncio
    async def test_annotation_context_query_count(self) -> None:
        """resolve_annotation_context() stays within query budget.

        Verifies the full page-load query path: workspace+template (1),
        placement JOIN (1), ACL (1), enrollment (1), staff roles (1),
        staff enrollment (1), admin users (1), tags (1), tag groups (1).
        """
        from uuid import uuid4

        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.engine import _state
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            resolve_annotation_context,
        )

        code = f"C{uuid4().hex[:6].upper()}"
        course = await create_course(
            code=code,
            name="Annotation Context Efficiency",
            semester="2026-S1",
        )
        week = await create_week(
            course_id=course.id,
            week_number=1,
            title="W1",
        )
        activity = await create_activity(
            week_id=week.id,
            title="A1",
        )
        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"ctx-{tag}@test.local",
            display_name=f"Context Tester {tag}",
        )
        ws, _id_map = await clone_workspace_from_activity(
            activity.id,
            user.id,
        )

        assert _state.engine is not None
        sync_engine = _state.engine.sync_engine

        with count_queries(sync_engine) as counter:
            ctx = await resolve_annotation_context(ws.id, user.id)

        assert ctx is not None
        # Budget: 9 queries for full activity-placed, non-admin path.
        # Before optimisation this was 11 (3 sequential gets + separate
        # template check). Regression guard: alert if queries creep up.
        assert len(counter) <= 9, (
            f"resolve_annotation_context() should need ≤9 queries, got {len(counter)}"
        )
