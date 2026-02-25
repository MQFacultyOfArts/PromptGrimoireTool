"""Integration tests for the navigator data loader.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify all navigator query sections (my_work, unstarted, shared_with_me,
shared_in_unit) and cursor pagination behaviour against the contract in Phase 3.

Self-contained tests create their own data; the scale test (AC5.5) uses
load-test data and skips when absent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from uuid import UUID

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


# ---------------------------------------------------------------------------
# Shared helper: create a full course/week/activity/student hierarchy
# ---------------------------------------------------------------------------


async def _create_course_with_sharing(tag: str, allow_sharing: bool) -> tuple:
    """Create course + published week + activity. Returns (course, week, activity)."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.weeks import create_week

    course = await create_course(
        code=f"N{tag[:6].upper()}", name=f"Nav Test {tag}", semester="2026-S1"
    )
    async with get_session() as session:
        session.add(course)
        course.default_allow_sharing = allow_sharing
        await session.flush()
        await session.refresh(course)

    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    async with get_session() as session:
        session.add(week)
        week.is_published = True
        await session.flush()
        await session.refresh(week)

    activity = await create_activity(week_id=week.id, title=f"Activity {tag}")
    return course, week, activity


async def _create_student_with_workspace(
    tag: str,
    index: int,
    course_id: UUID,
    activity_id: UUID,
    share_with_class: bool,
) -> tuple:
    """Create a student, enrol, and give them an owned workspace. Returns (user, ws)."""
    from promptgrimoire.db.acl import grant_permission
    from promptgrimoire.db.courses import enroll_user
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Workspace
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.workspaces import (
        create_workspace,
        place_workspace_in_activity,
    )

    student = await create_user(
        email=f"nav-stu-{index}-{tag}@test.local",
        display_name=f"Student {index} {tag}",
    )
    await enroll_user(course_id=course_id, user_id=student.id, role="student")

    ws = await create_workspace()
    await place_workspace_in_activity(ws.id, activity_id)
    await grant_permission(ws.id, student.id, "owner")
    async with get_session() as session:
        ws_obj = await session.get(Workspace, ws.id)
        assert ws_obj is not None
        ws_obj.title = f"Student {index} Work"
        ws_obj.shared_with_class = share_with_class
        session.add(ws_obj)
    return student, ws


async def _make_nav_data(
    *,
    allow_sharing: bool = True,
    num_students: int = 2,
    create_loose: bool = False,
    share_with_class: bool = True,
    create_shared_acl: bool = False,
    unpublished_activity: bool = False,
) -> dict:
    """Create a test hierarchy for navigator query tests.

    Returns dict with keys:
        course, week, activity, instructor, students (list),
        student_workspaces (dict: user_id -> workspace),
        template_workspace_id, loose_workspace (if create_loose),
        shared_workspace (if create_shared_acl),
    """
    from promptgrimoire.db.acl import grant_permission
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import enroll_user
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.weeks import create_week
    from promptgrimoire.db.workspaces import create_workspace, place_workspace_in_course

    tag = uuid4().hex[:8]
    course, week, activity = await _create_course_with_sharing(tag, allow_sharing)

    instructor = await create_user(
        email=f"nav-inst-{tag}@test.local", display_name=f"Instructor {tag}"
    )
    await enroll_user(course_id=course.id, user_id=instructor.id, role="coordinator")

    students = []
    student_workspaces: dict = {}
    for i in range(num_students):
        student, ws = await _create_student_with_workspace(
            tag, i, course.id, activity.id, share_with_class
        )
        students.append(student)
        student_workspaces[student.id] = ws

    result: dict = {
        "course": course,
        "week": week,
        "activity": activity,
        "instructor": instructor,
        "students": students,
        "student_workspaces": student_workspaces,
        "template_workspace_id": activity.template_workspace_id,
    }

    if create_loose and students:
        loose_ws = await create_workspace()
        await place_workspace_in_course(loose_ws.id, course.id)
        await grant_permission(loose_ws.id, students[0].id, "owner")
        async with get_session() as session:
            ws_obj = await session.get(
                __import__(
                    "promptgrimoire.db.models", fromlist=["Workspace"]
                ).Workspace,
                loose_ws.id,
            )
            assert ws_obj is not None
            ws_obj.title = "Loose Notes"
            session.add(ws_obj)
        result["loose_workspace"] = loose_ws

    if create_shared_acl and len(students) >= 2:
        ws_to_share = student_workspaces[students[0].id]
        await grant_permission(ws_to_share.id, students[1].id, "editor")
        result["shared_workspace"] = ws_to_share

    if unpublished_activity:
        week2 = await create_week(course_id=course.id, week_number=2, title="Week 2")
        unpub = await create_activity(week_id=week2.id, title=f"Unpub Activity {tag}")
        result["unpublished_activity"] = unpub
        result["week2"] = week2

    return result


# ===========================================================================
# Section 1: my_work
# ===========================================================================


class TestMyWork:
    """Tests for navigator section 1: my_work (AC1.1)."""

    @pytest.mark.asyncio
    async def test_owned_workspaces_appear(self) -> None:
        """Student sees owned workspaces with correct context.

        Verifies AC1.1.
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data()
        student = data["students"][0]
        ws = data["student_workspaces"][student.id]

        rows, _ = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[data["course"].id],
        )

        my_work_rows = [r for r in rows if r.section == "my_work"]
        my_work_ws_ids = {r.workspace_id for r in my_work_rows}
        assert ws.id in my_work_ws_ids

        # Verify context columns
        row = next(r for r in my_work_rows if r.workspace_id == ws.id)
        assert row.activity_title == data["activity"].title
        assert row.week_title == "Week 1"
        assert row.week_number == 1
        assert row.course_id == data["course"].id
        assert row.permission == "owner"

    @pytest.mark.asyncio
    async def test_template_excluded_from_my_work(self) -> None:
        """Template workspaces do not appear in my_work.

        Verifies template exclusion.
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data()
        student = data["students"][0]

        rows, _ = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[data["course"].id],
        )

        my_work_ws_ids = {r.workspace_id for r in rows if r.section == "my_work"}
        assert data["template_workspace_id"] not in my_work_ws_ids


# ===========================================================================
# Section 2: unstarted
# ===========================================================================


class TestUnstarted:
    """Tests for navigator section 2: unstarted (AC1.2)."""

    @pytest.mark.asyncio
    async def test_unstarted_activities_appear(self) -> None:
        """Activities without student workspace appear as unstarted.

        Verifies AC1.2.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.navigator import load_navigator_page
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week

        tag = uuid4().hex[:8]
        course = await create_course(
            code=f"U{tag[:6].upper()}", name="Unstarted Test", semester="2026-S1"
        )
        week = await create_week(course_id=course.id, week_number=1, title="Week 1")
        async with get_session() as session:
            session.add(week)
            week.is_published = True
            await session.flush()

        activity = await create_activity(week_id=week.id, title=f"Unstarted Act {tag}")
        student = await create_user(
            email=f"unstarted-{tag}@test.local", display_name=f"Unstarted {tag}"
        )
        await enroll_user(course_id=course.id, user_id=student.id, role="student")

        rows, _ = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[course.id],
        )

        unstarted_rows = [r for r in rows if r.section == "unstarted"]
        unstarted_act_ids = {r.activity_id for r in unstarted_rows}
        assert activity.id in unstarted_act_ids

        row = next(r for r in unstarted_rows if r.activity_id == activity.id)
        assert row.workspace_id is None
        assert row.permission is None

    @pytest.mark.asyncio
    async def test_unpublished_activity_excluded(self) -> None:
        """Unpublished activities do not appear as unstarted.

        Verifies AC1.2 (edge case).
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data(unpublished_activity=True)
        student = data["students"][0]

        rows, _ = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[data["course"].id],
        )

        unstarted_act_ids = {r.activity_id for r in rows if r.section == "unstarted"}
        assert data["unpublished_activity"].id not in unstarted_act_ids

    @pytest.mark.asyncio
    async def test_started_activity_not_unstarted(self) -> None:
        """Activity where user owns a workspace does not appear unstarted.

        Verifies AC1.2 (NOT EXISTS logic).
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data()
        student = data["students"][0]

        rows, _ = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[data["course"].id],
        )

        unstarted_act_ids = {r.activity_id for r in rows if r.section == "unstarted"}
        # Student 0 has a workspace for this activity, so not unstarted
        assert data["activity"].id not in unstarted_act_ids


# ===========================================================================
# Section 3: shared_with_me
# ===========================================================================


class TestSharedWithMe:
    """Tests for navigator section 3: shared_with_me (AC1.3)."""

    @pytest.mark.asyncio
    async def test_shared_editor_appears(self) -> None:
        """Workspace shared as editor appears in shared_with_me.

        Verifies AC1.3.
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data(create_shared_acl=True)
        recipient = data["students"][1]

        rows, _ = await load_navigator_page(
            user_id=recipient.id,
            is_privileged=False,
            enrolled_course_ids=[data["course"].id],
        )

        shared_rows = [r for r in rows if r.section == "shared_with_me"]
        shared_ws_ids = {r.workspace_id for r in shared_rows}
        assert data["shared_workspace"].id in shared_ws_ids

        row = next(
            r for r in shared_rows if r.workspace_id == data["shared_workspace"].id
        )
        assert row.permission == "editor"
        assert row.owner_user_id == data["students"][0].id
        assert row.owner_display_name == data["students"][0].display_name


# ===========================================================================
# Section 4: shared_in_unit
# ===========================================================================


class TestSharedInUnit:
    """Tests for navigator section 4: shared_in_unit (AC1.4, AC1.5)."""

    @pytest.mark.asyncio
    async def test_student_sees_peer_shared_workspaces(self) -> None:
        """Student sees shared_with_class=True workspaces from peers.

        Verifies AC1.4.
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data(share_with_class=True)
        student = data["students"][1]  # Not the workspace owner

        rows, _ = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[data["course"].id],
        )

        shared_rows = [r for r in rows if r.section == "shared_in_unit"]
        shared_ws_ids = {r.workspace_id for r in shared_rows}
        # Student 0's workspace should be visible to student 1
        assert data["student_workspaces"][data["students"][0].id].id in shared_ws_ids

    @pytest.mark.asyncio
    async def test_student_own_workspace_excluded(self) -> None:
        """Student does not see their own workspace in shared_in_unit.

        Verifies AC1.4 (own exclusion).
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data(share_with_class=True)
        student = data["students"][0]

        rows, _ = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[data["course"].id],
        )

        shared_rows = [r for r in rows if r.section == "shared_in_unit"]
        shared_ws_ids = {r.workspace_id for r in shared_rows}
        assert data["student_workspaces"][student.id].id not in shared_ws_ids

    @pytest.mark.asyncio
    async def test_sharing_disabled_excludes_peers(self) -> None:
        """Activity with allow_sharing=FALSE hides peer workspaces.

        Verifies AC1.4 (tristate).
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data(allow_sharing=False, share_with_class=True)
        student = data["students"][1]

        rows, _ = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[data["course"].id],
        )

        shared_rows = [r for r in rows if r.section == "shared_in_unit"]
        # No activity-placed peer workspaces should be visible
        activity_shared = [
            r for r in shared_rows if r.activity_id == data["activity"].id
        ]
        assert len(activity_shared) == 0

    @pytest.mark.asyncio
    async def test_instructor_sees_all_student_workspaces(self) -> None:
        """Instructor sees ALL student workspaces, not just shared ones.

        Verifies AC1.5.
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data(share_with_class=False)
        instructor = data["instructor"]

        rows, _ = await load_navigator_page(
            user_id=instructor.id,
            is_privileged=True,
            enrolled_course_ids=[data["course"].id],
        )

        shared_rows = [r for r in rows if r.section == "shared_in_unit"]
        shared_ws_ids = {r.workspace_id for r in shared_rows}
        # Instructor sees both student workspaces even when shared_with_class=False
        for student in data["students"]:
            ws = data["student_workspaces"][student.id]
            assert ws.id in shared_ws_ids

    # Zero-workspace student rows removed from navigator query — now served
    # by db.courses.list_students_without_workspaces() on the course detail page.
    # See #198 for proper analytics page.


# ===========================================================================
# Loose workspaces (AC1.6)
# ===========================================================================


class TestLooseWorkspaces:
    """Tests for loose workspaces (AC1.6)."""

    @pytest.mark.asyncio
    async def test_loose_workspace_in_my_work(self) -> None:
        """Loose workspace appears in my_work for the owner.

        Verifies AC1.6.
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data(create_loose=True)
        student = data["students"][0]

        rows, _ = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[data["course"].id],
        )

        my_work_ws_ids = {r.workspace_id for r in rows if r.section == "my_work"}
        assert data["loose_workspace"].id in my_work_ws_ids

    @pytest.mark.asyncio
    async def test_loose_workspace_in_shared_in_unit_for_instructor(self) -> None:
        """Instructor sees loose workspaces in shared_in_unit.

        Verifies AC1.6 (instructor view).
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data(create_loose=True)
        instructor = data["instructor"]

        rows, _ = await load_navigator_page(
            user_id=instructor.id,
            is_privileged=True,
            enrolled_course_ids=[data["course"].id],
        )

        shared_rows = [r for r in rows if r.section == "shared_in_unit"]
        shared_ws_ids = {r.workspace_id for r in shared_rows}
        assert data["loose_workspace"].id in shared_ws_ids


# ===========================================================================
# Empty sections (AC1.7)
# ===========================================================================


class TestEmptySections:
    """Tests for empty section behaviour (AC1.7)."""

    @pytest.mark.asyncio
    async def test_empty_sections_produce_zero_rows(self) -> None:
        """Sections with no matching data produce zero rows.

        Verifies AC1.7.
        """
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.navigator import load_navigator_page
        from promptgrimoire.db.users import create_user

        tag = uuid4().hex[:8]
        course = await create_course(
            code=f"E{tag[:6].upper()}", name="Empty Test", semester="2026-S1"
        )
        student = await create_user(
            email=f"nav-empty-sec-{tag}@test.local",
            display_name=f"Empty Sec {tag}",
        )
        await enroll_user(course_id=course.id, user_id=student.id, role="student")

        rows, cursor = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[course.id],
        )

        # No workspaces, no activities -> all sections empty
        assert len(rows) == 0
        assert cursor is None


# ===========================================================================
# Multi-course enrollment (AC1.8)
# ===========================================================================


async def _create_shared_peer_workspace(
    tag: str,
    label: str,
    course_id: UUID,
    activity_id: UUID,
) -> None:
    """Create a peer student with a shared workspace in the given activity."""
    from promptgrimoire.db.acl import grant_permission
    from promptgrimoire.db.courses import enroll_user
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Workspace
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.workspaces import (
        create_workspace,
        place_workspace_in_activity,
    )

    peer = await create_user(
        email=f"nav-multi-peer-{label}-{tag}@test.local",
        display_name=f"Peer {label} {tag}",
    )
    await enroll_user(course_id=course_id, user_id=peer.id, role="student")
    ws = await create_workspace()
    await place_workspace_in_activity(ws.id, activity_id)
    await grant_permission(ws.id, peer.id, "owner")
    async with get_session() as session:
        w = await session.get(Workspace, ws.id)
        assert w is not None
        w.shared_with_class = True
        session.add(w)


class TestMultiCourseEnrollment:
    """Tests for multi-course enrollment (AC1.8)."""

    @pytest.mark.asyncio
    async def test_multi_course_shared_in_unit(self) -> None:
        """Student enrolled in 2 courses sees distinct course_ids in shared_in_unit.

        Verifies AC1.8.
        """
        from promptgrimoire.db.courses import enroll_user
        from promptgrimoire.db.navigator import load_navigator_page
        from promptgrimoire.db.users import create_user

        tag = uuid4().hex[:8]

        course_a, _, act_a = await _create_course_with_sharing(f"ma{tag}", True)
        course_b, _, act_b = await _create_course_with_sharing(f"mb{tag}", True)

        viewer = await create_user(
            email=f"nav-multi-viewer-{tag}@test.local",
            display_name=f"Multi Viewer {tag}",
        )
        await enroll_user(course_id=course_a.id, user_id=viewer.id, role="student")
        await enroll_user(course_id=course_b.id, user_id=viewer.id, role="student")

        await _create_shared_peer_workspace(tag, "a", course_a.id, act_a.id)
        await _create_shared_peer_workspace(tag, "b", course_b.id, act_b.id)

        rows, _ = await load_navigator_page(
            user_id=viewer.id,
            is_privileged=False,
            enrolled_course_ids=[course_a.id, course_b.id],
        )

        shared_rows = [r for r in rows if r.section == "shared_in_unit"]
        course_ids = {r.course_id for r in shared_rows}
        assert course_a.id in course_ids
        assert course_b.id in course_ids


# ===========================================================================
# Cursor pagination (AC5.1, AC5.2, AC5.4)
# ===========================================================================


class TestCursorPagination:
    """Tests for keyset cursor pagination."""

    @pytest.mark.asyncio
    async def test_fewer_than_limit_no_cursor(self) -> None:
        """Fewer rows than limit returns all rows, cursor is None.

        Verifies AC5.4.
        """
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data(num_students=1)
        student = data["students"][0]

        rows, cursor = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[data["course"].id],
            limit=50,
        )

        assert len(rows) < 50
        assert cursor is None

    @pytest.mark.asyncio
    async def test_pagination_returns_cursor(self) -> None:
        """Exceeding limit returns cursor for next page.

        Verifies AC5.1.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.navigator import load_navigator_page
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        course = await create_course(
            code=f"P{tag[:6].upper()}", name="Paginate Test", semester="2026-S1"
        )
        async with get_session() as session:
            session.add(course)
            course.default_allow_sharing = True
            await session.flush()

        week = await create_week(course_id=course.id, week_number=1, title="Week 1")
        async with get_session() as session:
            session.add(week)
            week.is_published = True
            await session.flush()

        # Create 6 activities with 1 workspace each for a peer
        viewing_student = await create_user(
            email=f"nav-page-viewer-{tag}@test.local",
            display_name=f"Page Viewer {tag}",
        )
        await enroll_user(
            course_id=course.id, user_id=viewing_student.id, role="student"
        )

        peer = await create_user(
            email=f"nav-page-peer-{tag}@test.local",
            display_name=f"Page Peer {tag}",
        )
        await enroll_user(course_id=course.id, user_id=peer.id, role="student")

        for i in range(6):
            act = await create_activity(week_id=week.id, title=f"Page Act {i} {tag}")
            ws = await create_workspace()
            await place_workspace_in_activity(ws.id, act.id)
            await grant_permission(ws.id, peer.id, "owner")
            async with get_session() as session:
                w = await session.get(Workspace, ws.id)
                assert w is not None
                w.shared_with_class = True
                session.add(w)

        # Load with limit=3, should get cursor
        rows_p1, cursor_p1 = await load_navigator_page(
            user_id=viewing_student.id,
            is_privileged=False,
            enrolled_course_ids=[course.id],
            limit=3,
        )

        assert len(rows_p1) == 3
        assert cursor_p1 is not None

    @pytest.mark.asyncio
    async def test_pagination_no_duplicates(self) -> None:
        """Paginated pages have no duplicates or gaps.

        Verifies AC5.2.
        """
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.navigator import load_navigator_page
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        course = await create_course(
            code=f"D{tag[:6].upper()}", name="Dedup Test", semester="2026-S1"
        )
        async with get_session() as session:
            session.add(course)
            course.default_allow_sharing = True
            await session.flush()

        week = await create_week(course_id=course.id, week_number=1, title="Week 1")
        async with get_session() as session:
            session.add(week)
            week.is_published = True
            await session.flush()

        viewer = await create_user(
            email=f"nav-dedup-viewer-{tag}@test.local",
            display_name=f"Dedup Viewer {tag}",
        )
        await enroll_user(course_id=course.id, user_id=viewer.id, role="student")

        peer = await create_user(
            email=f"nav-dedup-peer-{tag}@test.local",
            display_name=f"Dedup Peer {tag}",
        )
        await enroll_user(course_id=course.id, user_id=peer.id, role="student")

        for i in range(8):
            act = await create_activity(week_id=week.id, title=f"Dedup Act {i} {tag}")
            ws = await create_workspace()
            await place_workspace_in_activity(ws.id, act.id)
            await grant_permission(ws.id, peer.id, "owner")
            async with get_session() as session:
                w = await session.get(Workspace, ws.id)
                assert w is not None
                w.shared_with_class = True
                session.add(w)

        # Collect all rows across pages
        all_row_ids: list = []
        cursor = None
        for _ in range(10):  # Safety limit
            rows, cursor = await load_navigator_page(
                user_id=viewer.id,
                is_privileged=False,
                enrolled_course_ids=[course.id],
                cursor=cursor,
                limit=3,
            )
            all_row_ids.extend(r.row_id for r in rows)
            if cursor is None:
                break

        # No duplicates
        assert len(all_row_ids) == len(set(all_row_ids))

        # Compare against a single large-limit fetch
        all_rows, _ = await load_navigator_page(
            user_id=viewer.id,
            is_privileged=False,
            enrolled_course_ids=[course.id],
            limit=100,
        )
        all_expected_ids = {r.row_id for r in all_rows}
        assert set(all_row_ids) == all_expected_ids


# ===========================================================================
# Activity-level sharing override (extra test)
# ===========================================================================


class TestActivitySharingOverride:
    """Tests for activity-level allow_sharing override."""

    @pytest.mark.asyncio
    async def test_activity_sharing_false_overrides_course_true(self) -> None:
        """Activity allow_sharing=FALSE overrides course default_allow_sharing=TRUE.

        No peer workspaces visible for that activity.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Activity
        from promptgrimoire.db.navigator import load_navigator_page

        data = await _make_nav_data(
            allow_sharing=True,  # Course default
            share_with_class=True,
        )

        # Override activity to disallow sharing
        async with get_session() as session:
            act = await session.get(Activity, data["activity"].id)
            assert act is not None
            act.allow_sharing = False
            session.add(act)

        student = data["students"][1]
        rows, _ = await load_navigator_page(
            user_id=student.id,
            is_privileged=False,
            enrolled_course_ids=[data["course"].id],
        )

        shared_rows = [
            r
            for r in rows
            if r.section == "shared_in_unit" and r.activity_id == data["activity"].id
        ]
        assert len(shared_rows) == 0


# ===========================================================================
# Scale test (AC5.5) - uses load-test data
# ===========================================================================


class TestScaleLoadTest:
    """Scale test using load-test data (AC5.5).

    Skipped when load-test data is absent.
    """

    @pytest.mark.asyncio
    async def test_instructor_query_at_scale(self) -> None:
        """Instructor query returns rows within acceptable time at 1100-student scale.

        Verifies AC5.5.
        """
        import time

        from sqlalchemy import func
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course, CourseEnrollment, User, Workspace
        from promptgrimoire.db.navigator import load_navigator_page

        # Guard: check load-test data is present
        async with get_session() as session:
            ws_count_result = await session.execute(
                select(func.count()).select_from(Workspace)
            )
            ws_count = ws_count_result.scalar()
            if ws_count is None or ws_count < 2000:
                pytest.skip("Load-test data not seeded (workspace count < 2000)")

        # Find instructor for LT-LAWS1100
        async with get_session() as session:
            result = await session.exec(
                select(User).where(User.email == "lt-instructor-torts@test.local")
            )
            instructor = result.first()
            if instructor is None:
                pytest.skip("Load-test instructor not found")

            # Get course IDs for instructor enrollments
            enrollment_result = await session.exec(
                select(CourseEnrollment.course_id).where(
                    CourseEnrollment.user_id == instructor.id
                )
            )
            enrolled_ids = list(enrollment_result.all())

            # Get the LAWS1100 course
            course_result = await session.exec(
                select(Course).where(Course.code == "LT-LAWS1100")
            )
            laws_course = course_result.first()
            if laws_course is None:
                pytest.skip("LT-LAWS1100 course not found")

        start = time.monotonic()
        rows, cursor = await load_navigator_page(
            user_id=instructor.id,
            is_privileged=True,
            enrolled_course_ids=enrolled_ids,
            limit=50,
        )
        elapsed = time.monotonic() - start

        assert len(rows) > 0
        assert elapsed < 5.0, f"Query took {elapsed:.2f}s, expected < 5s"

        # Verify cursor exists (should be more than 50 rows)
        if cursor is not None:
            # Load second page
            rows_p2, _ = await load_navigator_page(
                user_id=instructor.id,
                is_privileged=True,
                enrolled_course_ids=enrolled_ids,
                cursor=cursor,
                limit=50,
            )
            assert len(rows_p2) > 0
            # No duplicates between pages
            p1_ids = {r.row_id for r in rows}
            p2_ids = {r.row_id for r in rows_p2}
            assert p1_ids.isdisjoint(p2_ids)
