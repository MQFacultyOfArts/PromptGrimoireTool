"""Tests for anonymous_sharing tri-state resolution in PlacementContext.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify:
- AC4.1: Activity with anonymous_sharing=True hides author names from peer viewers
- AC4.2: Activity with anonymous_sharing=None inherits course.default_anonymous_sharing
- Explicit override: anonymous_sharing=False overrides course default
- Course-placed workspace inherits all course defaults (generalised fix)
- Loose workspace gets anonymous_sharing=False (default)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from promptgrimoire.db.workspaces import PlacementContext

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_anonymous_data(
    *,
    course_anonymous: bool = False,
    activity_anonymous: bool | None = None,
    course_copy_protection: bool = True,
    course_allow_sharing: bool = True,
) -> dict:
    """Create hierarchy for anonymous sharing tests.

    Returns course, activity, and the cloned workspace_id.
    """
    from promptgrimoire.db.activities import create_activity, update_activity
    from promptgrimoire.db.courses import create_course, enroll_user, update_course
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week, publish_week
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    tag = uuid4().hex[:8]

    course = await create_course(
        code=f"A{tag[:6].upper()}", name="Anon Test", semester="2026-S1"
    )
    await update_course(
        course.id,
        default_anonymous_sharing=course_anonymous,
        default_copy_protection=course_copy_protection,
        default_allow_sharing=course_allow_sharing,
    )

    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    await publish_week(week.id)

    activity = await create_activity(week_id=week.id, title="Anon Activity")
    await update_activity(activity.id, anonymous_sharing=activity_anonymous)

    owner = await create_user(
        email=f"anon-owner-{tag}@test.local", display_name=f"Anon Owner {tag}"
    )
    await enroll_user(course_id=course.id, user_id=owner.id, role="student")

    clone, _ = await clone_workspace_from_activity(activity.id, owner.id)

    return {
        "course": course,
        "activity": activity,
        "owner": owner,
        "workspace_id": clone.id,
    }


class TestAnonymousSharingTriState:
    """Tests for anonymous_sharing tri-state resolution in PlacementContext."""

    @pytest.mark.asyncio
    async def test_activity_anonymous_true(self) -> None:
        """Activity with anonymous_sharing=True resolves to True.

        Verifies workspace-sharing-97.AC4.1.
        """
        from promptgrimoire.db.workspaces import get_placement_context

        data = await _make_anonymous_data(
            course_anonymous=False, activity_anonymous=True
        )
        ctx = await get_placement_context(data["workspace_id"])
        assert ctx.anonymous_sharing is True

    @pytest.mark.asyncio
    async def test_activity_inherits_course_true(self) -> None:
        """Activity with anonymous_sharing=None inherits course default (True).

        Verifies workspace-sharing-97.AC4.2.
        """
        from promptgrimoire.db.workspaces import get_placement_context

        data = await _make_anonymous_data(
            course_anonymous=True, activity_anonymous=None
        )
        ctx = await get_placement_context(data["workspace_id"])
        assert ctx.anonymous_sharing is True

    @pytest.mark.asyncio
    async def test_activity_inherits_course_false(self) -> None:
        """Activity with anonymous_sharing=None inherits course default (False).

        Verifies workspace-sharing-97.AC4.2.
        """
        from promptgrimoire.db.workspaces import get_placement_context

        data = await _make_anonymous_data(
            course_anonymous=False, activity_anonymous=None
        )
        ctx = await get_placement_context(data["workspace_id"])
        assert ctx.anonymous_sharing is False

    @pytest.mark.asyncio
    async def test_activity_explicit_false_override(self) -> None:
        """Activity with anonymous_sharing=False overrides course default (True).

        Explicit override test.
        """
        from promptgrimoire.db.workspaces import get_placement_context

        data = await _make_anonymous_data(
            course_anonymous=True, activity_anonymous=False
        )
        ctx = await get_placement_context(data["workspace_id"])
        assert ctx.anonymous_sharing is False


async def _make_course_placed_workspace(**update_kwargs: Any) -> PlacementContext:
    """Create a course, set one default, place a workspace, return context."""
    from promptgrimoire.db.courses import create_course, update_course
    from promptgrimoire.db.workspaces import (
        create_workspace,
        get_placement_context,
        place_workspace_in_course,
    )

    tag = uuid4().hex[:8]
    course = await create_course(
        code=f"C{tag[:6].upper()}", name="Course Test", semester="2026-S1"
    )
    await update_course(course.id, **update_kwargs)

    ws = await create_workspace()
    await place_workspace_in_course(ws.id, course.id)

    return await get_placement_context(ws.id)


class TestCoursePlacementDefaults:
    """Tests for generalised course placement default propagation."""

    @pytest.mark.asyncio
    async def test_course_placed_inherits_anonymous_sharing(self) -> None:
        """Course-placed workspace inherits default_anonymous_sharing.

        Verifies generalised _resolve_course_placement propagation.
        """
        ctx = await _make_course_placed_workspace(default_anonymous_sharing=True)
        assert ctx.placement_type == "course"
        assert ctx.anonymous_sharing is True

    @pytest.mark.asyncio
    async def test_course_placed_inherits_copy_protection(self) -> None:
        """Course-placed workspace inherits default_copy_protection.

        Verifies generalised _resolve_course_placement propagation.
        """
        ctx = await _make_course_placed_workspace(default_copy_protection=True)
        assert ctx.placement_type == "course"
        assert ctx.copy_protection is True

    @pytest.mark.asyncio
    async def test_course_placed_inherits_allow_sharing(self) -> None:
        """Course-placed workspace inherits default_allow_sharing.

        Verifies generalised _resolve_course_placement propagation.
        """
        ctx = await _make_course_placed_workspace(default_allow_sharing=True)
        assert ctx.placement_type == "course"
        assert ctx.allow_sharing is True


class TestLooseWorkspaceDefaults:
    """Tests for loose workspace defaults."""

    @pytest.mark.asyncio
    async def test_loose_workspace_anonymous_sharing_default(self) -> None:
        """Loose workspace has anonymous_sharing=False (default)."""
        from promptgrimoire.db.workspaces import create_workspace, get_placement_context

        ws = await create_workspace()
        ctx = await get_placement_context(ws.id)
        assert ctx.placement_type == "loose"
        assert ctx.anonymous_sharing is False
