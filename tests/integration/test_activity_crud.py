"""Tests for Activity model, schema constraints, and FK behaviors.

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL.

Tests verify the Activity table schema, FK relationships, and cascade/set-null
behaviors at the database level. CRUD function tests are added in Task 6.
"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from promptgrimoire.db.models import Activity, Course, Week, Workspace

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)


async def _make_course_and_week(suffix: str = "") -> tuple[Course, Week]:
    """Create a course and week for activity tests with unique identifiers."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name=f"Test{suffix}", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course, week


class TestCreateActivity:
    """Tests for Activity model creation and schema constraints."""

    @pytest.mark.asyncio
    async def test_creates_with_uuid_and_timestamps(self) -> None:
        """Activity created with valid fields has auto-generated UUID and timestamps.

        Verifies AC1.1.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.workspaces import create_workspace

        _, week = await _make_course_and_week("uuid-ts")
        template = await create_workspace()

        async with get_session() as session:
            activity = Activity(
                week_id=week.id,
                template_workspace_id=template.id,
                title="Test Activity",
                description="A test activity",
            )
            session.add(activity)
            await session.flush()
            await session.refresh(activity)

            assert isinstance(activity.id, UUID)
            assert activity.created_at is not None
            assert activity.updated_at is not None
            assert activity.title == "Test Activity"
            assert activity.description == "A test activity"
            assert activity.week_id == week.id
            assert activity.template_workspace_id == template.id

    @pytest.mark.asyncio
    async def test_template_workspace_created_atomically(self) -> None:
        """Activity and its template workspace can be created in one transaction.

        Verifies AC1.2 at schema level -- the workspace exists and is referenced.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.workspaces import get_workspace

        _, week = await _make_course_and_week("atomic")

        async with get_session() as session:
            template = Workspace()
            session.add(template)
            await session.flush()

            activity = Activity(
                week_id=week.id,
                template_workspace_id=template.id,
                title="Atomic Test",
            )
            session.add(activity)
            await session.flush()
            await session.refresh(activity)

        # Verify template workspace exists in DB after transaction
        ws = await get_workspace(activity.template_workspace_id)
        assert ws is not None
        assert ws.id == template.id

    @pytest.mark.asyncio
    async def test_rejects_nonexistent_week_id(self) -> None:
        """Activity creation with non-existent week_id raises IntegrityError.

        Verifies AC1.3.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.workspaces import create_workspace

        template = await create_workspace()
        fake_week_id = uuid4()

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                activity = Activity(
                    week_id=fake_week_id,
                    template_workspace_id=template.id,
                    title="Should Fail",
                )
                session.add(activity)
                await session.flush()

    @pytest.mark.asyncio
    async def test_rejects_null_week_id(self) -> None:
        """Activity without week_id is rejected (NOT NULL constraint).

        Verifies AC1.4.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.workspaces import create_workspace

        template = await create_workspace()

        with pytest.raises(IntegrityError):
            async with get_session() as session:
                activity = Activity(
                    week_id=None,
                    template_workspace_id=template.id,
                    title="Should Fail",
                )
                session.add(activity)
                await session.flush()


class TestWorkspacePlacementFields:
    """Tests for Workspace placement fields at the database level."""

    @pytest.mark.asyncio
    async def test_workspace_has_activity_id_course_id_fields(self) -> None:
        """Workspace supports optional activity_id, course_id, enable_save_as_draft.

        Verifies AC1.5.
        """
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        workspace = await create_workspace()
        fetched = await get_workspace(workspace.id)
        assert fetched is not None
        assert fetched.activity_id is None
        assert fetched.course_id is None
        assert fetched.enable_save_as_draft is False

    @pytest.mark.asyncio
    async def test_check_constraint_rejects_both_activity_and_course(
        self,
    ) -> None:
        """DB CHECK constraint rejects workspace with both activity_id and course_id.

        Verifies AC1.6 at the database level. The Pydantic model_validator is
        tested in unit tests; this tests the CHECK constraint directly.

        Uses a raw session (not get_session) so the IntegrityError from flush()
        can be caught without conflicting with get_session's auto-commit.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.workspaces import create_workspace

        _, week = await _make_course_and_week("ck-both")
        course, _ = await _make_course_and_week("ck-both-2")

        # Create a workspace and an activity to get valid FKs
        template = await create_workspace()
        target = await create_workspace()

        # First transaction: create the activity
        async with get_session() as session:
            activity = Activity(
                week_id=week.id,
                template_workspace_id=template.id,
                title="For CK test",
            )
            session.add(activity)
            await session.flush()
            activity_id = activity.id

        # Second transaction: try to violate the CHECK constraint
        with pytest.raises(
            IntegrityError,
            match="ck_workspace_placement_exclusivity",
        ):
            async with get_session() as session:
                ws = await session.get(Workspace, target.id)
                assert ws is not None
                ws.activity_id = activity_id
                ws.course_id = course.id
                session.add(ws)
                await session.flush()


class TestCascadeBehavior:
    """Tests for FK cascade/set-null behaviors."""

    @pytest.mark.asyncio
    async def test_delete_activity_nulls_workspace_activity_id(self) -> None:
        """Deleting Activity sets workspace.activity_id to NULL (SET NULL).

        Verifies AC1.7.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        _, week = await _make_course_and_week("del-act-null")

        # Create template and activity
        template = await create_workspace()
        student_ws = await create_workspace()

        async with get_session() as session:
            activity = Activity(
                week_id=week.id,
                template_workspace_id=template.id,
                title="To Delete",
            )
            session.add(activity)
            await session.flush()
            activity_id = activity.id

            # Place student workspace in this activity
            ws = await session.get(Workspace, student_ws.id)
            assert ws is not None
            ws.activity_id = activity_id
            session.add(ws)
            await session.flush()

        # Verify workspace has activity_id set
        before = await get_workspace(student_ws.id)
        assert before is not None
        assert before.activity_id == activity_id

        # Delete activity first, then template (RESTRICT prevents reverse order)
        async with get_session() as session:
            act = await session.get(Activity, activity_id)
            assert act is not None
            template_id = act.template_workspace_id
            await session.delete(act)
            await session.flush()

            # Now safe to delete template workspace
            tmpl = await session.get(Workspace, template_id)
            if tmpl:
                await session.delete(tmpl)

        # Verify student workspace still exists with activity_id=None
        after = await get_workspace(student_ws.id)
        assert after is not None
        assert after.activity_id is None

    @pytest.mark.asyncio
    async def test_delete_course_nulls_workspace_course_id(self) -> None:
        """Deleting Course sets workspace.course_id to NULL (SET NULL).

        Verifies AC1.8.
        """
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.workspaces import create_workspace, get_workspace

        code = f"T{uuid4().hex[:6].upper()}"
        course = await create_course(code=code, name="To Delete", semester="2026-S1")
        ws = await create_workspace()

        # Set course_id on workspace
        async with get_session() as session:
            workspace = await session.get(Workspace, ws.id)
            assert workspace is not None
            workspace.course_id = course.id
            session.add(workspace)
            await session.flush()

        # Verify workspace has course_id set
        before = await get_workspace(ws.id)
        assert before is not None
        assert before.course_id == course.id

        # Delete the course
        async with get_session() as session:
            c = await session.get(Course, course.id)
            assert c is not None
            await session.delete(c)

        # Verify workspace still exists with course_id=None
        after = await get_workspace(ws.id)
        assert after is not None
        assert after.course_id is None

    @pytest.mark.asyncio
    async def test_delete_week_cascades_to_activity(self) -> None:
        """Deleting Week cascade-deletes its Activities.

        Activity.week_id has ondelete=CASCADE, so deleting the Week
        should remove the Activity too.
        """
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.weeks import delete_week
        from promptgrimoire.db.workspaces import create_workspace

        _, week = await _make_course_and_week("del-week-cas")
        template = await create_workspace()

        async with get_session() as session:
            activity = Activity(
                week_id=week.id,
                template_workspace_id=template.id,
                title="Will Cascade",
            )
            session.add(activity)
            await session.flush()
            activity_id = activity.id

        await delete_week(week.id)

        # Activity should be gone
        async with get_session() as session:
            act = await session.get(Activity, activity_id)
            assert act is None
