"""Integration tests for hybrid permission resolution.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Acceptance Criteria:
- AC6.1: User with explicit ACL entry gets that permission level
- AC6.2: Instructor enrolled in course gets Course.default_instructor_permission
- AC6.3: Coordinator enrolled in course gets access (same as instructor)
- AC6.4: Tutor enrolled in course gets access (same as instructor)
- AC6.5: When both explicit ACL and enrollment-derived exist, higher level wins
- AC6.6: Admin (via Stytch) gets owner-level access regardless of ACL/enrollment
- AC6.7: Student enrolled in course but without explicit ACL gets None
- AC6.8: Unenrolled user with no ACL entry gets None
- AC6.9: User with no auth session gets None
- AC6.10: Loose workspace -- only explicit ACL grants access
- AC6.11: Course-placed workspace -- instructor access derived from enrollment
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestExplicitACL:
    """AC6.1: User with explicit ACL entry gets that permission level."""

    @pytest.mark.asyncio
    async def test_explicit_viewer_acl(self) -> None:
        """User granted explicit 'viewer' ACL gets 'viewer' from resolve_permission."""
        from promptgrimoire.db.acl import grant_permission, resolve_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"resolve-explicit-{tag}@test.local",
            display_name=f"Explicit {tag}",
        )
        workspace = await create_workspace()
        await grant_permission(workspace.id, user.id, "viewer")

        result = await resolve_permission(workspace.id, user.id)

        assert result == "viewer"

    @pytest.mark.asyncio
    async def test_explicit_editor_acl(self) -> None:
        """User granted explicit 'editor' ACL gets 'editor'."""
        from promptgrimoire.db.acl import grant_permission, resolve_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"resolve-editor-{tag}@test.local",
            display_name=f"Editor {tag}",
        )
        workspace = await create_workspace()
        await grant_permission(workspace.id, user.id, "editor")

        result = await resolve_permission(workspace.id, user.id)

        assert result == "editor"

    @pytest.mark.asyncio
    async def test_explicit_owner_acl(self) -> None:
        """User granted explicit 'owner' ACL gets 'owner'."""
        from promptgrimoire.db.acl import grant_permission, resolve_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"resolve-owner-{tag}@test.local",
            display_name=f"Owner {tag}",
        )
        workspace = await create_workspace()
        await grant_permission(workspace.id, user.id, "owner")

        result = await resolve_permission(workspace.id, user.id)

        assert result == "owner"


class TestEnrollmentDerivedInstructor:
    """AC6.2: Instructor gets Course.default_instructor_permission."""

    @pytest.mark.asyncio
    async def test_instructor_gets_default_permission(self) -> None:
        """Instructor without explicit ACL gets default_instructor_permission."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        instructor = await create_user(
            email=f"resolve-instr-{tag}@test.local",
            display_name=f"Instructor {tag}",
        )
        course = await create_course(
            code=f"RES{tag[:4]}",
            name=f"Resolution Test {tag}",
            semester="2026-S1",
        )
        await enroll_user(course.id, instructor.id, role="instructor")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Test Activity")

        # Create a student workspace placed in this activity
        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)

        result = await resolve_permission(workspace.id, instructor.id)

        # Course default_instructor_permission is "editor"
        assert result == "editor"

    @pytest.mark.asyncio
    async def test_instructor_gets_custom_permission(self) -> None:
        """Instructor gets non-default permission when course overrides it."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        instructor = await create_user(
            email=f"resolve-custom-{tag}@test.local",
            display_name=f"Custom Perm {tag}",
        )
        course = await create_course(
            code=f"CUS{tag[:4]}",
            name=f"Custom Perm Test {tag}",
            semester="2026-S1",
        )
        # Override default_instructor_permission to "viewer"
        async with get_session() as session:
            db_course = await session.get(Course, course.id)
            assert db_course is not None
            db_course.default_instructor_permission = "viewer"
            session.add(db_course)
            await session.flush()

        await enroll_user(course.id, instructor.id, role="instructor")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Test Activity")

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)

        result = await resolve_permission(workspace.id, instructor.id)

        assert result == "viewer"

    @pytest.mark.asyncio
    async def test_instructor_on_template_workspace(self) -> None:
        """Instructor resolves permission on a template workspace."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week

        tag = uuid4().hex[:8]
        instructor = await create_user(
            email=f"resolve-tmpl-{tag}@test.local",
            display_name=f"Template {tag}",
        )
        course = await create_course(
            code=f"TPL{tag[:4]}",
            name=f"Template Test {tag}",
            semester="2026-S1",
        )
        await enroll_user(course.id, instructor.id, role="instructor")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Test Activity")

        # The template workspace is created by create_activity
        result = await resolve_permission(activity.template_workspace_id, instructor.id)

        assert result == "editor"


class TestEnrollmentDerivedCoordinator:
    """AC6.3: Coordinator enrolled in course gets access."""

    @pytest.mark.asyncio
    async def test_coordinator_gets_default_permission(self) -> None:
        """Coordinator derives 'editor' access from enrollment."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        coordinator = await create_user(
            email=f"resolve-coord-{tag}@test.local",
            display_name=f"Coordinator {tag}",
        )
        course = await create_course(
            code=f"CRD{tag[:4]}",
            name=f"Coord Test {tag}",
            semester="2026-S1",
        )
        await enroll_user(course.id, coordinator.id, role="coordinator")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Test Activity")

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)

        result = await resolve_permission(workspace.id, coordinator.id)

        assert result == "editor"


class TestEnrollmentDerivedTutor:
    """AC6.4: Tutor enrolled in course gets access."""

    @pytest.mark.asyncio
    async def test_tutor_gets_default_permission(self) -> None:
        """Tutor derives 'editor' access from enrollment."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        tutor = await create_user(
            email=f"resolve-tutor-{tag}@test.local",
            display_name=f"Tutor {tag}",
        )
        course = await create_course(
            code=f"TUT{tag[:4]}",
            name=f"Tutor Test {tag}",
            semester="2026-S1",
        )
        await enroll_user(course.id, tutor.id, role="tutor")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Test Activity")

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)

        result = await resolve_permission(workspace.id, tutor.id)

        assert result == "editor"


class TestHighestWins:
    """AC6.5: When both explicit ACL and enrollment-derived exist, higher level wins."""

    @pytest.mark.asyncio
    async def test_enrollment_derived_beats_explicit_viewer(self) -> None:
        """Instructor with explicit 'viewer' gets 'editor' (derived wins).

        Enrollment-derived 'editor' (level 20) > explicit 'viewer' (10).
        """
        from promptgrimoire.db.acl import grant_permission, resolve_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        instructor = await create_user(
            email=f"resolve-highest1-{tag}@test.local",
            display_name=f"Highest1 {tag}",
        )
        course = await create_course(
            code=f"HI1{tag[:4]}",
            name=f"Highest Test 1 {tag}",
            semester="2026-S1",
        )
        await enroll_user(course.id, instructor.id, role="instructor")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Test Activity")

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)

        # Explicit viewer (level 10) < derived editor (level 20)
        await grant_permission(workspace.id, instructor.id, "viewer")

        result = await resolve_permission(workspace.id, instructor.id)

        assert result == "editor"

    @pytest.mark.asyncio
    async def test_explicit_owner_beats_enrollment_derived(self) -> None:
        """Instructor with explicit 'owner' ACL gets 'owner' (explicit wins).

        Explicit 'owner' (level 30) > enrollment-derived 'editor' (level 20).
        """
        from promptgrimoire.db.acl import grant_permission, resolve_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        instructor = await create_user(
            email=f"resolve-highest2-{tag}@test.local",
            display_name=f"Highest2 {tag}",
        )
        course = await create_course(
            code=f"HI2{tag[:4]}",
            name=f"Highest Test 2 {tag}",
            semester="2026-S1",
        )
        await enroll_user(course.id, instructor.id, role="instructor")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Test Activity")

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)

        # Explicit owner (level 30) > derived editor (level 20)
        await grant_permission(workspace.id, instructor.id, "owner")

        result = await resolve_permission(workspace.id, instructor.id)

        assert result == "owner"


class TestStudentDenial:
    """AC6.7: Student enrolled in course but without explicit ACL gets None."""

    @pytest.mark.asyncio
    async def test_student_without_acl_gets_none(self) -> None:
        """Student enrolled in course gets None -- no derived access for students."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        student = await create_user(
            email=f"resolve-student-{tag}@test.local",
            display_name=f"Student {tag}",
        )
        course = await create_course(
            code=f"STU{tag[:4]}",
            name=f"Student Test {tag}",
            semester="2026-S1",
        )
        await enroll_user(course.id, student.id, role="student")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Test Activity")

        # Another user's workspace in the same activity
        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)

        result = await resolve_permission(workspace.id, student.id)

        assert result is None


class TestUnenrolledDenial:
    """AC6.8: Unenrolled user with no ACL entry gets None."""

    @pytest.mark.asyncio
    async def test_unenrolled_user_gets_none(self) -> None:
        """User not enrolled and without ACL gets None."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        outsider = await create_user(
            email=f"resolve-outsider-{tag}@test.local",
            display_name=f"Outsider {tag}",
        )
        course = await create_course(
            code=f"OUT{tag[:4]}",
            name=f"Outsider Test {tag}",
            semester="2026-S1",
        )
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Test Activity")

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)

        result = await resolve_permission(workspace.id, outsider.id)

        assert result is None


class TestLooseWorkspace:
    """AC6.10: Loose workspace -- only explicit ACL entries grant access."""

    @pytest.mark.asyncio
    async def test_loose_workspace_no_acl_returns_none(self) -> None:
        """Loose workspace with no ACL entry returns None (no enrollment derivation)."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"resolve-loose-none-{tag}@test.local",
            display_name=f"Loose None {tag}",
        )
        workspace = await create_workspace()

        result = await resolve_permission(workspace.id, user.id)

        assert result is None

    @pytest.mark.asyncio
    async def test_loose_workspace_with_acl_returns_permission(self) -> None:
        """Loose workspace with explicit ACL returns the granted permission."""
        from promptgrimoire.db.acl import grant_permission, resolve_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"resolve-loose-acl-{tag}@test.local",
            display_name=f"Loose ACL {tag}",
        )
        workspace = await create_workspace()
        await grant_permission(workspace.id, user.id, "editor")

        result = await resolve_permission(workspace.id, user.id)

        assert result == "editor"

    @pytest.mark.asyncio
    async def test_loose_workspace_instructor_enrolled_elsewhere(self) -> None:
        """Instructor enrolled in a course gets None on unrelated loose workspace."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        instructor = await create_user(
            email=f"resolve-loose-instr-{tag}@test.local",
            display_name=f"Loose Instr {tag}",
        )
        course = await create_course(
            code=f"LI{tag[:5]}",
            name=f"Loose Instr Test {tag}",
            semester="2026-S1",
        )
        await enroll_user(course.id, instructor.id, role="instructor")

        # Loose workspace -- not in any activity or course
        workspace = await create_workspace()

        result = await resolve_permission(workspace.id, instructor.id)

        assert result is None


class TestCoursePlacedWorkspace:
    """AC6.11: Course-placed workspace -- instructor derives access from enrollment."""

    @pytest.mark.asyncio
    async def test_instructor_on_course_placed_workspace(self) -> None:
        """Instructor gets 'editor' on workspace placed directly in their course."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_course,
        )

        tag = uuid4().hex[:8]
        instructor = await create_user(
            email=f"resolve-cplace-{tag}@test.local",
            display_name=f"Course Place {tag}",
        )
        course = await create_course(
            code=f"CP{tag[:5]}",
            name=f"Course Place Test {tag}",
            semester="2026-S1",
        )
        await enroll_user(course.id, instructor.id, role="instructor")

        workspace = await create_workspace()
        await place_workspace_in_course(workspace.id, course.id)

        result = await resolve_permission(workspace.id, instructor.id)

        assert result == "editor"

    @pytest.mark.asyncio
    async def test_student_on_course_placed_workspace_gets_none(self) -> None:
        """Student gets None on course-placed workspace (no derived access)."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_course,
        )

        tag = uuid4().hex[:8]
        student = await create_user(
            email=f"resolve-cplace-stu-{tag}@test.local",
            display_name=f"CPlace Student {tag}",
        )
        course = await create_course(
            code=f"CS{tag[:5]}",
            name=f"CPlace Student Test {tag}",
            semester="2026-S1",
        )
        await enroll_user(course.id, student.id, role="student")

        workspace = await create_workspace()
        await place_workspace_in_course(workspace.id, course.id)

        result = await resolve_permission(workspace.id, student.id)

        assert result is None


class TestAdminBypass:
    """AC6.6: Admin (via Stytch) gets owner-level access regardless of ACL/enrollment.

    The admin bypass lives at the page layer (is_privileged_user checks Stytch
    roles), not the DB layer (resolve_permission is pure data). These tests
    verify the building blocks: is_privileged_user returns True for admins,
    and resolve_permission returns None for users without ACL. The composition
    into check_workspace_access() is tested in Phase 8 (test_enforcement.py).
    """

    def test_admin_is_privileged(self) -> None:
        """is_privileged_user returns True for org-level admin."""
        from promptgrimoire.auth import is_privileged_user

        auth_user: dict[str, object] = {"is_admin": True, "roles": []}
        assert is_privileged_user(auth_user) is True

    def test_instructor_is_privileged(self) -> None:
        """is_privileged_user returns True for instructor role."""
        from promptgrimoire.auth import is_privileged_user

        auth_user: dict[str, object] = {"is_admin": False, "roles": ["instructor"]}
        assert is_privileged_user(auth_user) is True

    @pytest.mark.asyncio
    async def test_admin_without_acl_gets_none_from_db_layer(self) -> None:
        """resolve_permission returns None for admin without ACL entry.

        This confirms the DB layer does NOT handle admin bypass — that's
        the page layer's responsibility via is_privileged_user().
        """
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        admin = await create_user(
            email=f"admin-bypass-{tag}@test.local",
            display_name=f"Admin {tag}",
        )
        workspace = await create_workspace()

        # DB layer knows nothing about Stytch roles — returns None
        result = await resolve_permission(workspace.id, admin.id)
        assert result is None


class TestNoAuthDenial:
    """AC6.9: User with no auth session gets None.

    The "no auth session" check is at the page layer — resolve_permission()
    requires a user_id UUID, which can only come from an authenticated session.
    These tests verify the building blocks: is_privileged_user returns False
    for None, and resolve_permission rejects unknown user IDs. The composition
    into check_workspace_access() is tested in Phase 8 (test_enforcement.py).
    """

    def test_no_auth_user_is_not_privileged(self) -> None:
        """is_privileged_user returns False for None (unauthenticated)."""
        from promptgrimoire.auth import is_privileged_user

        assert is_privileged_user(None) is False

    @pytest.mark.asyncio
    async def test_unknown_user_id_gets_none(self) -> None:
        """resolve_permission returns None for a non-existent user UUID."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()
        result = await resolve_permission(workspace.id, uuid4())
        assert result is None


class TestStudentPeerAccess:
    """workspace-sharing-97.AC2.1: Enrolled student gets peer access."""

    @pytest.mark.asyncio
    async def test_student_peer_access(self) -> None:
        """Enrolled student + allow_sharing=True + shared_with_class=True -> 'peer'."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity, update_activity
        from promptgrimoire.db.courses import create_course, enroll_user, update_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        student = await create_user(
            email=f"peer-access-{tag}@test.local",
            display_name=f"Peer Student {tag}",
        )
        owner = await create_user(
            email=f"peer-owner-{tag}@test.local",
            display_name=f"Peer Owner {tag}",
        )
        course = await create_course(
            code=f"PA{tag[:5]}",
            name=f"Peer Access Test {tag}",
            semester="2026-S1",
        )
        await update_course(course.id, default_allow_sharing=True)
        await enroll_user(course.id, student.id, role="student")
        await enroll_user(course.id, owner.id, role="student")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Shared Activity")
        await update_activity(activity.id, allow_sharing=True)

        # Owner's workspace with sharing enabled
        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        async with get_session() as session:
            ws = await session.get(Workspace, workspace.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        result = await resolve_permission(workspace.id, student.id)

        assert result == "peer"


class TestStudentPeerDenied:
    """workspace-sharing-97.AC2.5 + AC2.6: Peer denied when conditions not met."""

    @pytest.mark.asyncio
    async def test_allow_sharing_false_denies_peer(self) -> None:
        """AC2.5: allow_sharing=False -> None even if shared_with_class=True."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity, update_activity
        from promptgrimoire.db.courses import create_course, enroll_user
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        student = await create_user(
            email=f"peer-deny-share-{tag}@test.local",
            display_name=f"Deny Share {tag}",
        )
        course = await create_course(
            code=f"PD{tag[:5]}",
            name=f"Peer Denied Share {tag}",
            semester="2026-S1",
        )
        await enroll_user(course.id, student.id, role="student")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="No Sharing")
        await update_activity(activity.id, allow_sharing=False)

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        async with get_session() as session:
            ws = await session.get(Workspace, workspace.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        result = await resolve_permission(workspace.id, student.id)

        assert result is None

    @pytest.mark.asyncio
    async def test_shared_with_class_false_denies_peer(self) -> None:
        """AC2.6: shared_with_class=False -> None even if allow_sharing=True."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity, update_activity
        from promptgrimoire.db.courses import create_course, enroll_user, update_course
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        student = await create_user(
            email=f"peer-deny-class-{tag}@test.local",
            display_name=f"Deny Class {tag}",
        )
        course = await create_course(
            code=f"PC{tag[:5]}",
            name=f"Peer Denied Class {tag}",
            semester="2026-S1",
        )
        await update_course(course.id, default_allow_sharing=True)
        await enroll_user(course.id, student.id, role="student")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Sharing Enabled")
        await update_activity(activity.id, allow_sharing=True)

        # shared_with_class defaults to False -- don't set it
        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)

        result = await resolve_permission(workspace.id, student.id)

        assert result is None


class TestStudentPeerTriState:
    """workspace-sharing-97.AC2.1 variant: tri-state inheritance for allow_sharing."""

    @pytest.mark.asyncio
    async def test_activity_inherits_course_default(self) -> None:
        """activity.allow_sharing=None + course.default_allow_sharing=True -> 'peer'."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.courses import create_course, enroll_user, update_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        student = await create_user(
            email=f"peer-tristate-{tag}@test.local",
            display_name=f"TriState {tag}",
        )
        course = await create_course(
            code=f"PT{tag[:5]}",
            name=f"Peer TriState {tag}",
            semester="2026-S1",
        )
        await update_course(course.id, default_allow_sharing=True)
        await enroll_user(course.id, student.id, role="student")
        week = await create_week(course.id, week_number=1, title="Week 1")
        # allow_sharing defaults to None (inherit from course)
        activity = await create_activity(week.id, title="Inherited Sharing")

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        async with get_session() as session:
            ws = await session.get(Workspace, workspace.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        result = await resolve_permission(workspace.id, student.id)

        assert result == "peer"


class TestStudentPeerLooseWorkspace:
    """workspace-sharing-97.AC2.7: Loose workspace -- no peer path."""

    @pytest.mark.asyncio
    async def test_loose_workspace_no_peer(self) -> None:
        """Loose workspace + shared_with_class=True -> None (no activity)."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.courses import create_course, enroll_user, update_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import create_workspace

        tag = uuid4().hex[:8]
        student = await create_user(
            email=f"peer-loose-{tag}@test.local",
            display_name=f"Loose Peer {tag}",
        )
        course = await create_course(
            code=f"PL{tag[:5]}",
            name=f"Peer Loose {tag}",
            semester="2026-S1",
        )
        await update_course(course.id, default_allow_sharing=True)
        await enroll_user(course.id, student.id, role="student")

        # Loose workspace (no activity_id, no course_id) with sharing
        workspace = await create_workspace()
        async with get_session() as session:
            ws = await session.get(Workspace, workspace.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        result = await resolve_permission(workspace.id, student.id)

        assert result is None


class TestStudentPeerCoursePlaced:
    """workspace-sharing-97.AC2.8: Course-placed workspace -- no peer discovery."""

    @pytest.mark.asyncio
    async def test_course_placed_no_peer(self) -> None:
        """Course-placed workspace + shared_with_class=True -> None."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.courses import create_course, enroll_user, update_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_course,
        )

        tag = uuid4().hex[:8]
        student = await create_user(
            email=f"peer-cplace-{tag}@test.local",
            display_name=f"CPlace Peer {tag}",
        )
        course = await create_course(
            code=f"PP{tag[:5]}",
            name=f"Peer CPlace {tag}",
            semester="2026-S1",
        )
        await update_course(course.id, default_allow_sharing=True)
        await enroll_user(course.id, student.id, role="student")

        workspace = await create_workspace()
        await place_workspace_in_course(workspace.id, course.id)
        async with get_session() as session:
            ws = await session.get(Workspace, workspace.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        result = await resolve_permission(workspace.id, student.id)

        assert result is None


class TestPeerVsExplicitACL:
    """AC2.2: Explicit ACL with higher permission wins over peer."""

    @pytest.mark.asyncio
    async def test_explicit_editor_beats_peer(self) -> None:
        """Student with explicit editor ACL + peer conditions met -> 'editor'."""
        from promptgrimoire.db.acl import grant_permission, resolve_permission
        from promptgrimoire.db.activities import create_activity, update_activity
        from promptgrimoire.db.courses import create_course, enroll_user, update_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        student = await create_user(
            email=f"peer-vs-acl-{tag}@test.local",
            display_name=f"Peer vs ACL {tag}",
        )
        course = await create_course(
            code=f"PV{tag[:5]}",
            name=f"Peer vs ACL Test {tag}",
            semester="2026-S1",
        )
        await update_course(course.id, default_allow_sharing=True)
        await enroll_user(course.id, student.id, role="student")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Shared Activity")
        await update_activity(activity.id, allow_sharing=True)

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        async with get_session() as session:
            ws = await session.get(Workspace, workspace.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        # Grant explicit editor ACL (level 20) -- beats peer (level 15)
        await grant_permission(workspace.id, student.id, "editor")

        result = await resolve_permission(workspace.id, student.id)

        assert result == "editor"


class TestOwnWorkspacePeer:
    """workspace-sharing-97.AC2.3: Student's own workspace returns owner, not peer."""

    @pytest.mark.asyncio
    async def test_owner_beats_peer(self) -> None:
        """Student who is owner (via ACL) + peer conditions met -> 'owner'."""
        from promptgrimoire.db.acl import grant_permission, resolve_permission
        from promptgrimoire.db.activities import create_activity, update_activity
        from promptgrimoire.db.courses import create_course, enroll_user, update_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"own-ws-peer-{tag}@test.local",
            display_name=f"Own WS Peer {tag}",
        )
        course = await create_course(
            code=f"OW{tag[:5]}",
            name=f"Own WS Peer Test {tag}",
            semester="2026-S1",
        )
        await update_course(course.id, default_allow_sharing=True)
        await enroll_user(course.id, owner.id, role="student")
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Shared Activity")
        await update_activity(activity.id, allow_sharing=True)

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        async with get_session() as session:
            ws = await session.get(Workspace, workspace.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        # Owner ACL (level 30) beats peer (level 15)
        await grant_permission(workspace.id, owner.id, "owner")

        result = await resolve_permission(workspace.id, owner.id)

        assert result == "owner"


class TestUnenrolledStudentPeer:
    """AC2.4: Unenrolled user gets None even if workspace is shared."""

    @pytest.mark.asyncio
    async def test_unenrolled_gets_none(self) -> None:
        """User not enrolled in course but workspace is shared -> None."""
        from promptgrimoire.db.acl import resolve_permission
        from promptgrimoire.db.activities import create_activity, update_activity
        from promptgrimoire.db.courses import create_course, update_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.weeks import create_week
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        tag = uuid4().hex[:8]
        outsider = await create_user(
            email=f"unenrolled-peer-{tag}@test.local",
            display_name=f"Unenrolled Peer {tag}",
        )
        course = await create_course(
            code=f"UP{tag[:5]}",
            name=f"Unenrolled Peer Test {tag}",
            semester="2026-S1",
        )
        await update_course(course.id, default_allow_sharing=True)
        # Deliberately NOT enrolling the outsider
        week = await create_week(course.id, week_number=1, title="Week 1")
        activity = await create_activity(week.id, title="Shared Activity")
        await update_activity(activity.id, allow_sharing=True)

        workspace = await create_workspace()
        await place_workspace_in_activity(workspace.id, activity.id)
        async with get_session() as session:
            ws = await session.get(Workspace, workspace.id)
            assert ws is not None
            ws.shared_with_class = True
            session.add(ws)

        result = await resolve_permission(workspace.id, outsider.id)

        assert result is None
