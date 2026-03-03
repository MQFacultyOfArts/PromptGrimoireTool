"""Integration tests for PageState word count population from PlacementContext.

Verifies that word count fields from PlacementContext flow through to
PageState construction, matching the path in _resolve_workspace_context().

Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _seed_activity_with_limits(
    *,
    word_minimum: int | None = None,
    word_limit: int | None = None,
    word_limit_enforcement: bool | None = None,
) -> tuple[UUID, UUID]:
    """Create Course -> Week -> Activity with word count fields.

    Returns (activity_id, workspace_id). Creates a workspace placed
    in the activity so get_placement_context can resolve the full
    hierarchy.
    """
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Activity as ActivityModel
    from promptgrimoire.db.weeks import create_week
    from promptgrimoire.db.workspaces import (
        create_workspace,
        place_workspace_in_activity,
    )

    code = f"PS{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name=f"PS Test {code}", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Word Count Test")

    # Set word count fields directly (create_activity may not expose all)
    async with get_session() as session:
        a = await session.get(ActivityModel, activity.id)
        assert a is not None
        if word_minimum is not None:
            a.word_minimum = word_minimum
        if word_limit is not None:
            a.word_limit = word_limit
        if word_limit_enforcement is not None:
            a.word_limit_enforcement = word_limit_enforcement
        session.add(a)

    ws = await create_workspace()
    await place_workspace_in_activity(ws.id, activity.id)
    return activity.id, ws.id


class TestPageStateWordCountFromPlacementContext:
    """Verify PlacementContext word count fields propagate to PageState.

    This tests the same data path as _resolve_workspace_context() without
    requiring the NiceGUI runtime (auth, storage, etc.). The production
    code reads ctx.word_minimum/word_limit/word_limit_enforcement and
    passes them to the PageState constructor.
    """

    @pytest.mark.asyncio
    async def test_word_limit_populates_pagestate(self) -> None:
        """Activity with word_limit=500 -> PageState.word_limit == 500."""
        from promptgrimoire.db.workspaces import get_placement_context
        from promptgrimoire.pages.annotation import PageState

        _, ws_id = await _seed_activity_with_limits(word_limit=500)
        ctx = await get_placement_context(ws_id)

        state = PageState(
            workspace_id=ws_id,
            word_minimum=ctx.word_minimum,
            word_limit=ctx.word_limit,
            word_limit_enforcement=ctx.word_limit_enforcement,
        )

        assert state.word_limit == 500
        assert state.word_minimum is None
        assert state.word_limit_enforcement is False

    @pytest.mark.asyncio
    async def test_word_minimum_populates_pagestate(self) -> None:
        """Activity with word_minimum=100 -> PageState.word_minimum == 100."""
        from promptgrimoire.db.workspaces import get_placement_context
        from promptgrimoire.pages.annotation import PageState

        _, ws_id = await _seed_activity_with_limits(word_minimum=100)
        ctx = await get_placement_context(ws_id)

        state = PageState(
            workspace_id=ws_id,
            word_minimum=ctx.word_minimum,
            word_limit=ctx.word_limit,
            word_limit_enforcement=ctx.word_limit_enforcement,
        )

        assert state.word_minimum == 100
        assert state.word_limit is None

    @pytest.mark.asyncio
    async def test_both_limits_and_enforcement_populate_pagestate(self) -> None:
        """All three word count fields populate PageState."""
        from promptgrimoire.db.workspaces import get_placement_context
        from promptgrimoire.pages.annotation import PageState

        _, ws_id = await _seed_activity_with_limits(
            word_minimum=100,
            word_limit=500,
            word_limit_enforcement=True,
        )
        ctx = await get_placement_context(ws_id)

        state = PageState(
            workspace_id=ws_id,
            word_minimum=ctx.word_minimum,
            word_limit=ctx.word_limit,
            word_limit_enforcement=ctx.word_limit_enforcement,
        )

        assert state.word_minimum == 100
        assert state.word_limit == 500
        assert state.word_limit_enforcement is True

    @pytest.mark.asyncio
    async def test_no_limits_leaves_pagestate_defaults(self) -> None:
        """Activity with no word count fields -> PageState defaults (None/False)."""
        from promptgrimoire.db.workspaces import get_placement_context
        from promptgrimoire.pages.annotation import PageState

        _, ws_id = await _seed_activity_with_limits()
        ctx = await get_placement_context(ws_id)

        state = PageState(
            workspace_id=ws_id,
            word_minimum=ctx.word_minimum,
            word_limit=ctx.word_limit,
            word_limit_enforcement=ctx.word_limit_enforcement,
        )

        assert state.word_minimum is None
        assert state.word_limit is None
        assert state.word_limit_enforcement is False
