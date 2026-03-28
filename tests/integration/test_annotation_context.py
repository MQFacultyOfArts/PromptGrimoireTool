"""Tests for resolve_annotation_context().

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Each test creates its own data via UUID isolation — no cross-test interference.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


class TestResolveAnnotationContextActivityPlaced:
    """Tests for activity-placed workspace resolution."""

    @pytest.mark.asyncio
    async def test_activity_placed_workspace(self) -> None:
        """Activity-placed workspace resolves full hierarchy."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Activity, Course, Week, Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            resolve_annotation_context,
        )

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"ctx-act-{tag}@test.local",
            display_name=f"Ctx Act {tag}",
        )

        # Build hierarchy: Course -> Week -> Activity -> Workspace
        async with get_session() as session:
            course = Course(
                id=uuid4(),
                code=f"TST-{tag[:6]}",
                name="Test Course",
                semester="2026-S1",
            )
            session.add(course)
            await session.flush()

            week = Week(
                id=uuid4(),
                course_id=course.id,
                week_number=1,
                title="Week 1",
            )
            session.add(week)
            await session.flush()

            # Create the template workspace first (annotation activity requires it)
            template_ws = await create_workspace()

            activity = Activity(
                id=uuid4(),
                week_id=week.id,
                type="annotation",
                template_workspace_id=template_ws.id,
                title="Test Activity",
            )
            session.add(activity)
            await session.flush()

            # Create the student workspace placed in this activity
            ws = await create_workspace()

            # Update workspace activity_id directly
            db_ws = await session.get(Workspace, ws.id)
            assert db_ws is not None
            db_ws.activity_id = activity.id
            session.add(db_ws)
            await session.flush()

            ws_id = ws.id
            activity_title = activity.title
            course_code = course.code
            course_name = course.name
            week_number = week.week_number

        await grant_permission(ws_id, user.id, "owner")

        ctx = await resolve_annotation_context(ws_id, user.id)

        assert ctx is not None
        assert ctx.placement.placement_type == "activity"
        assert ctx.placement.activity_title == activity_title
        assert ctx.placement.course_code == course_code
        assert ctx.placement.course_name == course_name
        assert ctx.placement.week_number == week_number
        assert ctx.permission == "owner"


class TestResolveAnnotationContextCoursePlaced:
    """Tests for course-placed workspace resolution."""

    @pytest.mark.asyncio
    async def test_course_placed_workspace(self) -> None:
        """Course-placed workspace resolves course fields only."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course, Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            resolve_annotation_context,
        )

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"ctx-crs-{tag}@test.local",
            display_name=f"Ctx Crs {tag}",
        )

        async with get_session() as session:
            course = Course(
                id=uuid4(),
                code=f"CRS-{tag[:6]}",
                name="Course Placed Test",
                semester="2026-S1",
            )
            session.add(course)
            await session.flush()

            ws = await create_workspace()
            db_ws = await session.get(Workspace, ws.id)
            assert db_ws is not None
            db_ws.course_id = course.id
            session.add(db_ws)
            await session.flush()

            ws_id = ws.id
            course_code = course.code
            course_name = course.name

        await grant_permission(ws_id, user.id, "owner")

        ctx = await resolve_annotation_context(ws_id, user.id)

        assert ctx is not None
        assert ctx.placement.placement_type == "course"
        assert ctx.placement.course_code == course_code
        assert ctx.placement.course_name == course_name
        assert ctx.placement.activity_title is None
        assert ctx.placement.week_number is None


class TestResolveAnnotationContextStandalone:
    """Tests for standalone (loose) workspace resolution."""

    @pytest.mark.asyncio
    async def test_standalone_workspace(self) -> None:
        """Standalone workspace has loose placement."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            resolve_annotation_context,
        )

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"ctx-loose-{tag}@test.local",
            display_name=f"Ctx Loose {tag}",
        )

        ws = await create_workspace()
        await grant_permission(ws.id, user.id, "owner")

        ctx = await resolve_annotation_context(ws.id, user.id)

        assert ctx is not None
        assert ctx.placement.placement_type == "loose"
        assert ctx.placement.activity_title is None
        assert ctx.placement.week_number is None
        assert ctx.placement.course_code is None
        assert ctx.placement.course_name is None


class TestResolveAnnotationContextTemplate:
    """Tests for template workspace detection."""

    @pytest.mark.asyncio
    async def test_template_activity_placed(self) -> None:
        """Activity-placed template detected via activity.template_workspace_id."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Activity, Course, Week, Workspace
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            resolve_annotation_context,
        )

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"ctx-tmpl-{tag}@test.local",
            display_name=f"Ctx Tmpl {tag}",
        )

        async with get_session() as session:
            course = Course(
                id=uuid4(),
                code=f"TMP-{tag[:6]}",
                name="Template Test",
                semester="2026-S1",
            )
            session.add(course)
            await session.flush()

            week = Week(
                id=uuid4(),
                course_id=course.id,
                week_number=1,
                title="Week 1",
            )
            session.add(week)
            await session.flush()

            # The template workspace IS the workspace under test
            template_ws = await create_workspace()

            activity = Activity(
                id=uuid4(),
                week_id=week.id,
                type="annotation",
                template_workspace_id=template_ws.id,
                title="Template Activity",
            )
            session.add(activity)
            await session.flush()

            # Place the template workspace in the activity
            db_ws = await session.get(Workspace, template_ws.id)
            assert db_ws is not None
            db_ws.activity_id = activity.id
            session.add(db_ws)
            await session.flush()

            ws_id = template_ws.id

        await grant_permission(ws_id, user.id, "owner")

        ctx = await resolve_annotation_context(ws_id, user.id)

        assert ctx is not None
        assert ctx.placement.is_template is True
        assert ctx.placement.placement_type == "activity"

    @pytest.mark.asyncio
    async def test_template_standalone(self) -> None:
        """Standalone template detected via reverse lookup."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Activity, Course, Week
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            resolve_annotation_context,
        )

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"ctx-tmpl-sa-{tag}@test.local",
            display_name=f"Ctx Tmpl SA {tag}",
        )

        # Create a standalone workspace, then point an activity's template to it
        template_ws = await create_workspace()

        async with get_session() as session:
            course = Course(
                id=uuid4(),
                code=f"TSA-{tag[:6]}",
                name="Standalone Template Test",
                semester="2026-S1",
            )
            session.add(course)
            await session.flush()

            week = Week(
                id=uuid4(),
                course_id=course.id,
                week_number=1,
                title="Week 1",
            )
            session.add(week)
            await session.flush()

            activity = Activity(
                id=uuid4(),
                week_id=week.id,
                type="annotation",
                template_workspace_id=template_ws.id,
                title="Points To Standalone",
            )
            session.add(activity)
            await session.flush()

        await grant_permission(template_ws.id, user.id, "owner")

        ctx = await resolve_annotation_context(template_ws.id, user.id)

        assert ctx is not None
        assert ctx.placement.is_template is True
        # Workspace itself has no activity_id, so placement is loose
        assert ctx.placement.placement_type == "loose"


class TestResolveAnnotationContextPermission:
    """Tests for permission resolution."""

    @pytest.mark.asyncio
    async def test_explicit_acl_permission(self) -> None:
        """Explicit ACL entry returns correct permission."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            resolve_annotation_context,
        )

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"ctx-perm-{tag}@test.local",
            display_name=f"Ctx Perm {tag}",
        )

        ws = await create_workspace()
        await grant_permission(ws.id, user.id, "editor")

        ctx = await resolve_annotation_context(ws.id, user.id)

        assert ctx is not None
        assert ctx.permission == "editor"

    @pytest.mark.asyncio
    async def test_admin_bypass(self) -> None:
        """Admin bypass returns owner regardless of ACL."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            resolve_annotation_context,
        )

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"ctx-admin-{tag}@test.local",
            display_name=f"Ctx Admin {tag}",
        )

        ws = await create_workspace()
        # No ACL entry for this user

        ctx = await resolve_annotation_context(ws.id, user.id, is_admin=True)

        assert ctx is not None
        assert ctx.permission == "owner"

    @pytest.mark.asyncio
    async def test_default_deny_no_acl_no_enrollment(self) -> None:
        """User with no ACL and no enrollment gets None permission."""
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            resolve_annotation_context,
        )

        tag = uuid4().hex[:8]
        user = await create_user(
            email=f"ctx-deny-{tag}@test.local",
            display_name=f"Ctx Deny {tag}",
        )

        ws = await create_workspace()
        # No ACL entry, no enrollment — default deny

        ctx = await resolve_annotation_context(ws.id, user.id)

        assert ctx is not None
        assert ctx.permission is None


class TestResolveAnnotationContextPrivilegedUsers:
    """Tests for privileged user ID resolution."""

    @pytest.mark.asyncio
    async def test_privileged_users_includes_staff(self) -> None:
        """Staff enrolled in course appear in privileged_user_ids."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import (
            Activity,
            Course,
            CourseEnrollment,
            Week,
            Workspace,
        )
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            resolve_annotation_context,
        )

        tag = uuid4().hex[:8]
        owner = await create_user(
            email=f"ctx-priv-owner-{tag}@test.local",
            display_name=f"Ctx Priv Owner {tag}",
        )
        instructor = await create_user(
            email=f"ctx-priv-instr-{tag}@test.local",
            display_name=f"Ctx Priv Instr {tag}",
        )

        async with get_session() as session:
            course = Course(
                id=uuid4(),
                code=f"PRV-{tag[:6]}",
                name="Privileged Test",
                semester="2026-S1",
            )
            session.add(course)
            await session.flush()

            enrollment = CourseEnrollment(
                id=uuid4(),
                course_id=course.id,
                user_id=instructor.id,
                role="instructor",
            )
            session.add(enrollment)
            await session.flush()

            week = Week(
                id=uuid4(),
                course_id=course.id,
                week_number=1,
                title="Week 1",
            )
            session.add(week)
            await session.flush()

            template_ws = await create_workspace()

            activity = Activity(
                id=uuid4(),
                week_id=week.id,
                type="annotation",
                template_workspace_id=template_ws.id,
                title="Privileged Activity",
            )
            session.add(activity)
            await session.flush()

            ws = await create_workspace()
            db_ws = await session.get(Workspace, ws.id)
            assert db_ws is not None
            db_ws.activity_id = activity.id
            session.add(db_ws)
            await session.flush()

            ws_id = ws.id

        await grant_permission(ws_id, owner.id, "owner")

        ctx = await resolve_annotation_context(ws_id, owner.id)

        assert ctx is not None
        assert str(instructor.id) in ctx.privileged_user_ids


class TestResolveAnnotationContextTags:
    """Tests for tag and tag group resolution."""

    @pytest.mark.asyncio
    async def test_tags_and_tag_groups(self) -> None:
        """Tags and tag groups returned in order."""
        from promptgrimoire.db.acl import grant_permission
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Tag, TagGroup
        from promptgrimoire.db.users import create_user
        from promptgrimoire.db.workspaces import (
            create_workspace,
            resolve_annotation_context,
        )

        tag_hex = uuid4().hex[:8]
        user = await create_user(
            email=f"ctx-tags-{tag_hex}@test.local",
            display_name=f"Ctx Tags {tag_hex}",
        )

        ws = await create_workspace()
        await grant_permission(ws.id, user.id, "owner")

        async with get_session() as session:
            group = TagGroup(
                id=uuid4(),
                workspace_id=ws.id,
                name=f"Group-{tag_hex}",
                order_index=0,
            )
            session.add(group)
            await session.flush()

            tag_a = Tag(
                id=uuid4(),
                workspace_id=ws.id,
                group_id=group.id,
                name=f"TagA-{tag_hex}",
                color="#1f77b4",
                order_index=0,
            )
            tag_b = Tag(
                id=uuid4(),
                workspace_id=ws.id,
                group_id=group.id,
                name=f"TagB-{tag_hex}",
                color="#ff7f0e",
                order_index=1,
            )
            session.add(tag_a)
            session.add(tag_b)
            await session.flush()

            tag_a_name = tag_a.name
            tag_b_name = tag_b.name
            group_name = group.name

        ctx = await resolve_annotation_context(ws.id, user.id)

        assert ctx is not None
        assert len(ctx.tags) == 2
        assert ctx.tags[0].name == tag_a_name
        assert ctx.tags[1].name == tag_b_name
        assert len(ctx.tag_groups) == 1
        assert ctx.tag_groups[0].name == group_name


class TestResolveAnnotationContextNonexistent:
    """Tests for nonexistent workspace handling."""

    @pytest.mark.asyncio
    async def test_nonexistent_workspace(self) -> None:
        """Nonexistent workspace returns None."""
        from promptgrimoire.db.workspaces import resolve_annotation_context

        result = await resolve_annotation_context(uuid4(), uuid4())

        assert result is None
