"""Integration tests for word count fields in PlacementContext resolution.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Verifies AC2.4 (PlacementContext resolves enforcement via resolve_tristate)
and AC2.6 (no limits configured = no word count behaviour).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import Course, Week

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_and_week(
    suffix: str,
    *,
    default_word_limit_enforcement: bool = False,
) -> tuple[Course, Week]:
    """Create Course (with word limit enforcement setting) and Week."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.weeks import create_week

    code = f"WC{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code,
        name=f"WC Test {suffix}",
        semester="2026-S1",
    )

    if default_word_limit_enforcement:
        async with get_session() as session:
            c = await session.get(Course, course.id)
            assert c is not None
            c.default_word_limit_enforcement = default_word_limit_enforcement
            session.add(c)
            await session.flush()
        # Session committed on exit; re-read to confirm
        async with get_session() as session:
            refreshed = await session.get(Course, course.id)
            assert refreshed is not None
            course = refreshed

    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course, week


class TestPlacementContextWordCountResolution:
    """Tests for word count field resolution in PlacementContext.

    Verifies AC2.4: PlacementContext resolves enforcement via resolve_tristate.
    """

    @pytest.mark.asyncio
    async def test_activity_override_true_enforcement_is_hard(self) -> None:
        """AC2.4: Activity enforcement=True overrides course default=False.

        Result: enforcement is True (hard limit).
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Activity as ActivityModel
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _, week = await _make_course_and_week(
            "enf-true", default_word_limit_enforcement=False
        )
        activity = await create_activity(
            week_id=week.id,
            title="Hard Limit",
        )
        # Set word_limit_enforcement directly since create_activity doesn't expose it
        async with get_session() as session:
            a = await session.get(ActivityModel, activity.id)
            assert a is not None
            a.word_limit_enforcement = True
            a.word_minimum = 100
            a.word_limit = 500
            session.add(a)

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.word_limit_enforcement is True
        assert ctx.word_minimum == 100
        assert ctx.word_limit == 500

    @pytest.mark.asyncio
    async def test_activity_override_none_inherits_course_default_false(self) -> None:
        """AC2.4: Activity enforcement=None, course default=False -> False (soft)."""
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _, week = await _make_course_and_week(
            "enf-inherit-false", default_word_limit_enforcement=False
        )
        activity = await create_activity(week_id=week.id, title="Inherit Soft")

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.word_limit_enforcement is False

    @pytest.mark.asyncio
    async def test_activity_override_false_overrides_course_true(self) -> None:
        """AC2.4: Activity enforcement=False overrides course default=True.

        Activity-level override wins.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Activity as ActivityModel
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _, week = await _make_course_and_week(
            "enf-override", default_word_limit_enforcement=True
        )
        activity = await create_activity(week_id=week.id, title="Override Soft")
        async with get_session() as session:
            a = await session.get(ActivityModel, activity.id)
            assert a is not None
            a.word_limit_enforcement = False
            session.add(a)

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.word_limit_enforcement is False

    @pytest.mark.asyncio
    async def test_no_limits_configured(self) -> None:
        """AC2.6: Activity with no word count fields set -> all None/default."""
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _, week = await _make_course_and_week("no-limits")
        activity = await create_activity(week_id=week.id, title="No Limits")

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.word_minimum is None
        assert ctx.word_limit is None
        assert ctx.word_limit_enforcement is False  # inherited from course default


class TestPlacementContextWordCountEdgeCases:
    """Edge case tests for word count fields in PlacementContext.

    Verifies AC2.4 and AC2.6 edge cases: course placement, loose placement,
    and partial limit configurations.
    """

    @pytest.mark.asyncio
    async def test_course_placed_workspace_uses_course_defaults(self) -> None:
        """Course-placed workspace: no activity limits, enforcement=course default."""
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_course,
        )

        course, _ = await _make_course_and_week(
            "course-placed", default_word_limit_enforcement=True
        )
        ws = await create_workspace()
        await place_workspace_in_course(ws.id, course.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.word_minimum is None
        assert ctx.word_limit is None
        assert ctx.word_limit_enforcement is True  # course default

    @pytest.mark.asyncio
    async def test_loose_workspace_has_no_limits(self) -> None:
        """Loose workspace: no limits, enforcement=False (dataclass default)."""
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
        )

        ws = await create_workspace()
        ctx = await get_placement_context(ws.id)

        assert ctx.word_minimum is None
        assert ctx.word_limit is None
        assert ctx.word_limit_enforcement is False

    @pytest.mark.asyncio
    async def test_activity_with_minimum_only(self) -> None:
        """Activity with word_minimum=100 but no word_limit -> word_limit stays None."""
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Activity as ActivityModel
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _, week = await _make_course_and_week("min-only")
        activity = await create_activity(week_id=week.id, title="Min Only")
        async with get_session() as session:
            a = await session.get(ActivityModel, activity.id)
            assert a is not None
            a.word_minimum = 100
            session.add(a)

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.word_minimum == 100
        assert ctx.word_limit is None

    @pytest.mark.asyncio
    async def test_activity_with_limit_only(self) -> None:
        """Activity with word_limit but no word_minimum.

        word_minimum stays None.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Activity as ActivityModel
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _, week = await _make_course_and_week("limit-only")
        activity = await create_activity(week_id=week.id, title="Limit Only")
        async with get_session() as session:
            a = await session.get(ActivityModel, activity.id)
            assert a is not None
            a.word_limit = 500
            session.add(a)

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.word_minimum is None
        assert ctx.word_limit == 500
