"""Integration tests for tag creation settings in CRUD functions.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify:
- AC8.1: Activity CRUD accepts and persists allow_tag_creation
- AC8.2: Course CRUD accepts and persists default_allow_tag_creation
- AC8.3-8.5: Tri-state inheritance round-trip through CRUD update functions
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_and_week(suffix: str = "") -> tuple:
    """Create a course and week for activity tests with unique identifiers.

    Returns (course, week) tuple.
    """
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code, name=f"TagSettings{suffix}", semester="2026-S1"
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course, week


class TestCreateActivityWithTagCreation:
    """Tests for create_activity with allow_tag_creation parameter.

    Verifies AC8.1.
    """

    @pytest.mark.asyncio
    async def test_create_with_allow_tag_creation_false(self) -> None:
        """create_activity with allow_tag_creation=False persists the value.

        Verifies AC8.1.
        """
        from promptgrimoire.db.activities import create_activity, get_activity

        _, week = await _make_course_and_week("create-false")

        activity = await create_activity(
            week_id=week.id,
            title="No Tag Creation",
            allow_tag_creation=False,
        )
        assert activity.allow_tag_creation is False

        refetched = await get_activity(activity.id)
        assert refetched is not None
        assert refetched.allow_tag_creation is False

    @pytest.mark.asyncio
    async def test_create_without_allow_tag_creation_defaults_none(self) -> None:
        """create_activity without allow_tag_creation defaults to None (inherit).

        Verifies AC8.1.
        """
        from promptgrimoire.db.activities import create_activity, get_activity

        _, week = await _make_course_and_week("create-default")

        activity = await create_activity(
            week_id=week.id,
            title="Default Activity",
        )
        assert activity.allow_tag_creation is None

        refetched = await get_activity(activity.id)
        assert refetched is not None
        assert refetched.allow_tag_creation is None


class TestUpdateActivityTagCreation:
    """Tests for update_activity with allow_tag_creation parameter.

    Verifies AC8.1.
    """

    @pytest.mark.asyncio
    async def test_update_allow_tag_creation_to_false(self) -> None:
        """update_activity sets allow_tag_creation to False.

        Verifies AC8.1.
        """
        from promptgrimoire.db.activities import (
            create_activity,
            get_activity,
            update_activity,
        )

        _, week = await _make_course_and_week("update-false")

        activity = await create_activity(week_id=week.id, title="Will Disable Tags")
        assert activity.allow_tag_creation is None

        updated = await update_activity(activity.id, allow_tag_creation=False)
        assert updated is not None
        assert updated.allow_tag_creation is False

        refetched = await get_activity(activity.id)
        assert refetched is not None
        assert refetched.allow_tag_creation is False

    @pytest.mark.asyncio
    async def test_update_allow_tag_creation_reset_to_none(self) -> None:
        """update_activity resets allow_tag_creation to None (inherit).

        Verifies AC8.1.
        """
        from promptgrimoire.db.activities import (
            create_activity,
            get_activity,
            update_activity,
        )

        _, week = await _make_course_and_week("update-reset")

        activity = await create_activity(
            week_id=week.id,
            title="Will Reset Tags",
            allow_tag_creation=False,
        )
        assert activity.allow_tag_creation is False

        updated = await update_activity(activity.id, allow_tag_creation=None)
        assert updated is not None
        assert updated.allow_tag_creation is None

        refetched = await get_activity(activity.id)
        assert refetched is not None
        assert refetched.allow_tag_creation is None

    @pytest.mark.asyncio
    async def test_update_title_only_preserves_allow_tag_creation(self) -> None:
        """update_activity with only title does NOT change allow_tag_creation.

        Verifies Ellipsis sentinel correctly distinguishes "not provided" from None.
        """
        from promptgrimoire.db.activities import (
            create_activity,
            get_activity,
            update_activity,
        )

        _, week = await _make_course_and_week("update-title-only")

        activity = await create_activity(
            week_id=week.id,
            title="Original",
            allow_tag_creation=False,
        )
        assert activity.allow_tag_creation is False

        updated = await update_activity(activity.id, title="Renamed")
        assert updated is not None
        assert updated.title == "Renamed"
        assert updated.allow_tag_creation is False

        refetched = await get_activity(activity.id)
        assert refetched is not None
        assert refetched.allow_tag_creation is False


class TestUpdateCourseDefaultTagCreation:
    """Tests for update_course with default_allow_tag_creation parameter.

    Verifies AC8.2.
    """

    @pytest.mark.asyncio
    async def test_update_default_allow_tag_creation_to_false(self) -> None:
        """update_course sets default_allow_tag_creation to False.

        Verifies AC8.2.
        """
        from promptgrimoire.db.courses import (
            create_course,
            get_course_by_id,
            update_course,
        )

        code = f"T{uuid4().hex[:6].upper()}"
        course = await create_course(code=code, name="Tag Course", semester="2026-S1")
        assert course.default_allow_tag_creation is True  # default

        updated = await update_course(course.id, default_allow_tag_creation=False)
        assert updated is not None
        assert updated.default_allow_tag_creation is False

        refetched = await get_course_by_id(course.id)
        assert refetched is not None
        assert refetched.default_allow_tag_creation is False

    @pytest.mark.asyncio
    async def test_update_default_allow_tag_creation_to_true(self) -> None:
        """update_course sets default_allow_tag_creation to True.

        Verifies AC8.2.
        """
        from promptgrimoire.db.courses import (
            create_course,
            get_course_by_id,
            update_course,
        )

        code = f"T{uuid4().hex[:6].upper()}"
        course = await create_course(code=code, name="Tag Course 2", semester="2026-S1")

        # First set to False
        await update_course(course.id, default_allow_tag_creation=False)

        # Then set back to True
        updated = await update_course(course.id, default_allow_tag_creation=True)
        assert updated is not None
        assert updated.default_allow_tag_creation is True

        refetched = await get_course_by_id(course.id)
        assert refetched is not None
        assert refetched.default_allow_tag_creation is True

    @pytest.mark.asyncio
    async def test_update_name_only_preserves_default_allow_tag_creation(self) -> None:
        """update_course with only name does NOT change default_allow_tag_creation.

        Verifies Ellipsis sentinel works correctly for course settings.
        """
        from promptgrimoire.db.courses import (
            create_course,
            get_course_by_id,
            update_course,
        )

        code = f"T{uuid4().hex[:6].upper()}"
        course = await create_course(
            code=code, name="Original Name", semester="2026-S1"
        )

        # Set to False first
        await update_course(course.id, default_allow_tag_creation=False)

        # Update name only
        updated = await update_course(course.id, name="New Name")
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.default_allow_tag_creation is False

        refetched = await get_course_by_id(course.id)
        assert refetched is not None
        assert refetched.default_allow_tag_creation is False


class TestTriStateInheritanceFromCrud:
    """Tests for tri-state inheritance exercised through CRUD update functions.

    These verify AC8.3-8.5 via round-trip: update via CRUD then
    verify via PlacementContext.
    """

    @pytest.mark.asyncio
    async def test_activity_none_inherits_course_true(self) -> None:
        """Activity allow_tag_creation=None inherits course default=True.

        Verifies AC8.3.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user, update_course
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week, publish_week
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            get_placement_context,
        )

        tag = uuid4().hex[:8]
        code = f"T{uuid4().hex[:6].upper()}"
        course = await create_course(code=code, name="AC83", semester="2026-S1")
        await update_course(course.id, default_allow_tag_creation=True)

        week = await create_week(course_id=course.id, week_number=1, title="Week 1")
        await publish_week(week.id)

        activity = await create_activity(
            week_id=week.id,
            title="Inherit Test",
            allow_tag_creation=None,
        )

        owner = await create_user(
            email=f"ac83-{tag}@test.local", display_name=f"AC83 {tag}"
        )
        await enroll_user(course_id=course.id, user_id=owner.id, role="student")

        clone, _ = await clone_workspace_from_activity(activity.id, owner.id)
        ctx = await get_placement_context(clone.id)
        assert ctx.allow_tag_creation is True

    @pytest.mark.asyncio
    async def test_activity_true_overrides_course_false(self) -> None:
        """Activity allow_tag_creation=True overrides course default=False.

        Verifies AC8.4.
        """
        from promptgrimoire.db.activities import create_activity, update_activity
        from promptgrimoire.db.courses import create_course, enroll_user, update_course
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week, publish_week
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            get_placement_context,
        )

        tag = uuid4().hex[:8]
        code = f"T{uuid4().hex[:6].upper()}"
        course = await create_course(code=code, name="AC84", semester="2026-S1")
        await update_course(course.id, default_allow_tag_creation=False)

        week = await create_week(course_id=course.id, week_number=1, title="Week 1")
        await publish_week(week.id)

        activity = await create_activity(week_id=week.id, title="Override True")
        await update_activity(activity.id, allow_tag_creation=True)

        owner = await create_user(
            email=f"ac84-{tag}@test.local", display_name=f"AC84 {tag}"
        )
        await enroll_user(course_id=course.id, user_id=owner.id, role="student")

        clone, _ = await clone_workspace_from_activity(activity.id, owner.id)
        ctx = await get_placement_context(clone.id)
        assert ctx.allow_tag_creation is True

    @pytest.mark.asyncio
    async def test_activity_false_overrides_course_true(self) -> None:
        """Activity allow_tag_creation=False overrides course default=True.

        Verifies AC8.5.
        """
        from promptgrimoire.db.activities import create_activity, update_activity
        from promptgrimoire.db.courses import create_course, enroll_user, update_course
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week, publish_week
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            get_placement_context,
        )

        tag = uuid4().hex[:8]
        code = f"T{uuid4().hex[:6].upper()}"
        course = await create_course(code=code, name="AC85", semester="2026-S1")
        await update_course(course.id, default_allow_tag_creation=True)

        week = await create_week(course_id=course.id, week_number=1, title="Week 1")
        await publish_week(week.id)

        activity = await create_activity(week_id=week.id, title="Override False")
        await update_activity(activity.id, allow_tag_creation=False)

        owner = await create_user(
            email=f"ac85-{tag}@test.local", display_name=f"AC85 {tag}"
        )
        await enroll_user(course_id=course.id, user_id=owner.id, role="student")

        clone, _ = await clone_workspace_from_activity(activity.id, owner.id)
        ctx = await get_placement_context(clone.id)
        assert ctx.allow_tag_creation is False
