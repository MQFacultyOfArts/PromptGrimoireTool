"""Tests for workspace listing queries.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify student accessible workspaces (AC9.1, AC9.2), instructor course
view (AC9.3, AC9.4), Resume/Start detection (AC9.5, AC9.6), and orphaned
workspace persistence (AC9.7).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_listing_data() -> dict:
    """Create hierarchy for listing query tests.

    Returns course, activity, student_a (owner of clone), student_b
    (shared viewer), loose workspace owned by student_a.
    """
    from promptgrimoire.db.acl import grant_permission, grant_share
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course, enroll_user
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week, publish_week
    from promptgrimoire.db.workspaces import (
        clone_workspace_from_activity,
        create_workspace,
        place_workspace_in_course,
    )

    tag = uuid4().hex[:8]

    course = await create_course(
        code=f"L{tag[:6].upper()}", name="Listing Test", semester="2026-S1"
    )
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    await publish_week(week.id)

    activity = await create_activity(week_id=week.id, title="List Activity")

    student_a = await create_user(
        email=f"stu-a-{tag}@test.local", display_name=f"StudentA {tag}"
    )
    await enroll_user(course_id=course.id, user_id=student_a.id, role="student")

    student_b = await create_user(
        email=f"stu-b-{tag}@test.local", display_name=f"StudentB {tag}"
    )
    await enroll_user(course_id=course.id, user_id=student_b.id, role="student")

    # student_a clones the activity
    clone, _ = await clone_workspace_from_activity(activity.id, student_a.id)

    # student_a shares clone with student_b as viewer
    await grant_share(
        clone.id,
        student_a.id,
        student_b.id,
        "viewer",
        sharing_allowed=True,
    )

    # Create a loose workspace owned by student_a
    loose = await create_workspace()
    await place_workspace_in_course(loose.id, course.id)
    await grant_permission(loose.id, student_a.id, "owner")

    return {
        "course": course,
        "activity": activity,
        "student_a": student_a,
        "student_b": student_b,
        "clone": clone,
        "loose": loose,
    }


class TestListAccessibleWorkspaces:
    """Tests for list_accessible_workspaces() — student my-workspaces view."""

    @pytest.mark.asyncio
    async def test_owner_sees_cloned_workspace(self) -> None:
        """Student sees their owned (cloned) workspace.

        Verifies AC9.1.
        """
        from promptgrimoire.db.acl import list_accessible_workspaces

        data = await _make_listing_data()
        results = await list_accessible_workspaces(data["student_a"].id)
        ws_ids = {ws.id for ws, _perm in results}
        assert data["clone"].id in ws_ids

    @pytest.mark.asyncio
    async def test_owner_sees_loose_workspace(self) -> None:
        """Student sees their owned loose workspace.

        Verifies AC9.1.
        """
        from promptgrimoire.db.acl import list_accessible_workspaces

        data = await _make_listing_data()
        results = await list_accessible_workspaces(data["student_a"].id)
        ws_ids = {ws.id for ws, _perm in results}
        assert data["loose"].id in ws_ids

    @pytest.mark.asyncio
    async def test_shared_viewer_sees_workspace(self) -> None:
        """Student sees workspaces shared with them.

        Verifies AC9.2.
        """
        from promptgrimoire.db.acl import list_accessible_workspaces

        data = await _make_listing_data()
        results = await list_accessible_workspaces(data["student_b"].id)
        ws_map = {ws.id: perm for ws, perm in results}
        assert data["clone"].id in ws_map
        assert ws_map[data["clone"].id] == "viewer"

    @pytest.mark.asyncio
    async def test_orphaned_workspace_still_accessible(self) -> None:
        """Workspace persists in list after activity deletion.

        Verifies AC9.7.
        """
        from promptgrimoire.db.acl import list_accessible_workspaces
        from promptgrimoire.db.activities import delete_activity

        data = await _make_listing_data()
        await delete_activity(data["activity"].id)

        results = await list_accessible_workspaces(data["student_a"].id)
        ws_ids = {ws.id for ws, _perm in results}
        assert data["clone"].id in ws_ids


class TestListCourseWorkspaces:
    """Tests for list_course_workspaces() — instructor view."""

    @pytest.mark.asyncio
    async def test_includes_student_clone(self) -> None:
        """Instructor sees student's cloned workspace.

        Verifies AC9.3.
        """
        from promptgrimoire.db.acl import list_course_workspaces

        data = await _make_listing_data()
        results = await list_course_workspaces(data["course"].id)
        ws_ids = {ws.id for ws in results}
        assert data["clone"].id in ws_ids

    @pytest.mark.asyncio
    async def test_excludes_template(self) -> None:
        """Template workspace is excluded from instructor view.

        Verifies AC9.3 (template exclusion).
        """
        from promptgrimoire.db.acl import list_course_workspaces
        from promptgrimoire.db.activities import get_activity

        data = await _make_listing_data()
        activity = await get_activity(data["activity"].id)
        assert activity is not None
        results = await list_course_workspaces(data["course"].id)
        ws_ids = {ws.id for ws in results}
        assert activity.template_workspace_id not in ws_ids

    @pytest.mark.asyncio
    async def test_includes_loose_workspace(self) -> None:
        """Instructor sees loose workspaces in course.

        Verifies AC9.4.
        """
        from promptgrimoire.db.acl import list_course_workspaces

        data = await _make_listing_data()
        results = await list_course_workspaces(data["course"].id)
        ws_ids = {ws.id for ws in results}
        assert data["loose"].id in ws_ids


class TestResumeDetection:
    """Tests for get_user_workspace_for_activity() Resume vs Start."""

    @pytest.mark.asyncio
    async def test_owner_gets_resume(self) -> None:
        """Owner of cloned workspace gets it back (Resume).

        Verifies AC9.5.
        """
        from promptgrimoire.db.workspaces import get_user_workspace_for_activity

        data = await _make_listing_data()
        result = await get_user_workspace_for_activity(
            data["activity"].id, data["student_a"].id
        )
        assert result is not None
        assert result.id == data["clone"].id

    @pytest.mark.asyncio
    async def test_shared_viewer_gets_start(self) -> None:
        """Viewer of shared workspace gets None (Start Activity).

        Verifies AC9.6 — shared viewer didn't clone, so they should
        see Start Activity, not Resume.
        """
        from promptgrimoire.db.workspaces import get_user_workspace_for_activity

        data = await _make_listing_data()
        result = await get_user_workspace_for_activity(
            data["activity"].id, data["student_b"].id
        )
        assert result is None
