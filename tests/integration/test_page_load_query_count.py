"""Page-load query count regression test.

Measures the total number of SQL round-trips during an actual NiceGUI
annotation page load.  Asserts a ceiling that prevents reintroduction
of redundant queries.

Uses SQLAlchemy engine-level instrumentation (before_cursor_execute),
not function-level mocking, so it catches ALL database round-trips
regardless of which function issues them.

Requires DEV__TEST_DATABASE_URL and a running PostgreSQL instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from tests.integration.conftest import _authenticate
from tests.integration.nicegui_helpers import (
    _should_see_testid,
    wait_for_annotation_load,
)
from tests.integration.test_query_efficiency import count_queries

if TYPE_CHECKING:
    from nicegui.testing.user import User

pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    pytest.mark.nicegui_ui,
]


# ---------------------------------------------------------------------------
# DB helpers (reused from test_multi_doc_tabs.py pattern)
# ---------------------------------------------------------------------------


async def _create_course() -> tuple[UUID, str]:
    from promptgrimoire.db.courses import create_course

    uid = uuid4().hex[:8]
    code = f"QRY{uid.upper()}"
    course = await create_course(
        code=code,
        name=f"Query Count Test {uid}",
        semester="2026-S1",
    )
    return course.id, code


async def _enroll(course_id: UUID, email: str, role: str) -> UUID:
    from promptgrimoire.db.courses import enroll_user
    from promptgrimoire.db.users import create_user

    user = await create_user(email=email, display_name=email.split("@", maxsplit=1)[0])
    await enroll_user(course_id, user.id, role)
    return user.id


async def _setup_single_doc_workspace(email: str) -> UUID:
    """Create a workspace with one document for page-load measurement.

    Returns workspace_id for the cloned student workspace.
    """
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.weeks import create_week, publish_week
    from promptgrimoire.db.workspace_documents import add_document
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    course_id, _ = await _create_course()
    await _enroll(course_id, "coord-qry@test.example.edu.au", "coordinator")
    user_id = await _enroll(course_id, email, "student")

    week = await create_week(course_id=course_id, week_number=1, title="Week 1")
    await publish_week(week.id)

    activity = await create_activity(week_id=week.id, title="Query Count Activity")

    await add_document(
        workspace_id=activity.template_workspace_id,
        type="source",
        content="<p>Sample document for query counting.</p>",
        source_type="paste",
        title="Query Test Doc",
    )

    ws, _doc_map = await clone_workspace_from_activity(activity.id, user_id)
    return ws.id


class TestPageLoadQueryCeiling:
    """Verify total DB round-trips during annotation page load.

    The ceiling prevents reintroduction of redundant queries.
    It counts ALL queries (including CRDT, tags, ACL) — not just
    document fetches — so it catches any new redundancy anywhere
    in the page-load path.
    """

    @pytest.mark.asyncio
    async def test_single_doc_page_load_query_ceiling(self, nicegui_user: User) -> None:
        """Total DB queries during page load must not exceed ceiling.

        The ceiling is set at the expected post-optimisation count.
        If this test fails, a new redundant query was introduced.

        Current expected queries (single-doc workspace):
        1. get_workspace (entry point)
        2. check_workspace_access (ACL)
        3. get_placement_context
        4. get_privileged_user_ids_for_workspace
        5. list_document_headers
        6. CRDT load (get_or_create_for_workspace)
        7. list_tags_for_workspace (CRDT consistency)
        8. list_tag_groups_for_workspace (CRDT consistency)
        9. get_document (first doc, for rendering)
        10. check_existing_export (header)
        """
        from promptgrimoire.db.engine import _state

        email = f"qry-ceil-{uuid4().hex[:6]}@test.example.edu.au"
        ws_id = await _setup_single_doc_workspace(email)

        await _authenticate(nicegui_user, email=email)

        assert _state.engine is not None, "Engine not initialised"
        sync_engine = _state.engine.sync_engine

        # Count ALL queries during page load
        with count_queries(sync_engine) as counter:
            await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
            await wait_for_annotation_load(nicegui_user)
            await _should_see_testid(nicegui_user, "doc-container")

        # Baseline measured at 32 SQL statements (2026-03-27).
        # Includes implicit session management, multi-step placement
        # context (5 sequential GETs), CRDT load, tag consistency, etc.
        #
        # Three redundant calls identified:
        # - list_document_headers() called twice (~1 SQL each)
        # - get_document(first) called twice (~1 SQL each)
        # - get_placement_context() called twice (~5 SQL each)
        # Removing these should save ~7 SQL statements: 32 → ~25.
        #
        # Ceiling set at 25 to catch reintroduction.
        # If this fails HIGH, a new redundant query was added.
        # If this fails LOW, the ceiling can be tightened.
        query_count = len(counter)
        assert query_count <= 25, (
            f"Page load should execute ≤25 DB queries, got {query_count}. "
            f"Check for redundant fetches in the annotation page-load path."
        )
