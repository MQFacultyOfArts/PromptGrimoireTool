"""Integration tests for word count fields.

Tests PlacementContext resolution and update_activity() word count support.
Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Verifies AC2.1, AC2.2, AC2.4, AC2.5, AC2.6.
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


class TestUpdateActivityWordCountFields:
    """Tests for word count field support in update_activity().

    Verifies AC2.1 (fields accept int|None), AC2.2 (enforcement tri-state),
    AC2.5 (cross-field validation).
    """

    @pytest.mark.asyncio
    async def test_set_word_minimum(self) -> None:
        """AC2.1: Set word_minimum via update_activity, read back."""
        from promptgrimoire.db.activities import create_activity, update_activity

        _, week = await _make_course_and_week("upd-min")
        activity = await create_activity(week_id=week.id, title="Set Min")

        updated = await update_activity(activity.id, word_minimum=100)
        assert updated is not None
        assert updated.word_minimum == 100

    @pytest.mark.asyncio
    async def test_set_word_limit(self) -> None:
        """AC2.1: Set word_limit via update_activity, read back."""
        from promptgrimoire.db.activities import create_activity, update_activity

        _, week = await _make_course_and_week("upd-lim")
        activity = await create_activity(week_id=week.id, title="Set Limit")

        updated = await update_activity(activity.id, word_limit=500)
        assert updated is not None
        assert updated.word_limit == 500

    @pytest.mark.asyncio
    async def test_set_word_limit_enforcement_true(self) -> None:
        """AC2.2: Set word_limit_enforcement=True, read back."""
        from promptgrimoire.db.activities import create_activity, update_activity

        _, week = await _make_course_and_week("upd-enf-true")
        activity = await create_activity(week_id=week.id, title="Hard Enforce")

        updated = await update_activity(activity.id, word_limit_enforcement=True)
        assert updated is not None
        assert updated.word_limit_enforcement is True

    @pytest.mark.asyncio
    async def test_reset_word_limit_enforcement_to_inherit(self) -> None:
        """AC2.2: Reset word_limit_enforcement=None (inherit), read back."""
        from promptgrimoire.db.activities import create_activity, update_activity

        _, week = await _make_course_and_week("upd-enf-reset")
        activity = await create_activity(week_id=week.id, title="Reset Enforce")

        # Set to True first
        await update_activity(activity.id, word_limit_enforcement=True)
        # Reset to None (inherit)
        updated = await update_activity(activity.id, word_limit_enforcement=None)
        assert updated is not None
        assert updated.word_limit_enforcement is None

    @pytest.mark.asyncio
    async def test_validation_rejects_minimum_ge_limit(self) -> None:
        """AC2.5: Setting word_minimum >= word_limit via update raises ValueError."""
        from promptgrimoire.db.activities import create_activity, update_activity

        _, week = await _make_course_and_week("upd-val-reject")
        activity = await create_activity(week_id=week.id, title="Validate")

        with pytest.raises(
            ValueError, match="word_minimum must be less than word_limit"
        ):
            await update_activity(activity.id, word_minimum=500, word_limit=200)

    @pytest.mark.asyncio
    async def test_validation_rejects_when_updating_one_field(self) -> None:
        """AC2.5: Updating just word_minimum to exceed existing word_limit raises."""
        from promptgrimoire.db.activities import create_activity, update_activity

        _, week = await _make_course_and_week("upd-val-partial")
        activity = await create_activity(week_id=week.id, title="Partial Val")

        # Set word_limit first
        await update_activity(activity.id, word_limit=200)
        # Now try to set word_minimum higher than the existing limit
        with pytest.raises(
            ValueError, match="word_minimum must be less than word_limit"
        ):
            await update_activity(activity.id, word_minimum=300)

    @pytest.mark.asyncio
    async def test_omitted_fields_unchanged(self) -> None:
        """Omitting word count params preserves existing values."""
        from promptgrimoire.db.activities import (
            create_activity,
            get_activity,
            update_activity,
        )

        _, week = await _make_course_and_week("upd-preserve")
        activity = await create_activity(week_id=week.id, title="Preserve")

        # Set word count fields
        await update_activity(
            activity.id, word_minimum=100, word_limit=500, word_limit_enforcement=True
        )

        # Update only title -- word count fields should be unchanged
        await update_activity(activity.id, title="Renamed")

        refetched = await get_activity(activity.id)
        assert refetched is not None
        assert refetched.word_minimum == 100
        assert refetched.word_limit == 500
        assert refetched.word_limit_enforcement is True
