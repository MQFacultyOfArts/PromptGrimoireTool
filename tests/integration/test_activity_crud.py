"""Tests for Activity model, schema constraints, FK behaviors, and CRUD operations.

These tests require a running PostgreSQL instance. Set TEST_DATABASE_URL.

Tests verify the Activity table schema, FK relationships, cascade/set-null
behaviors at the database level, and CRUD function correctness.
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


class TestActivityCRUD:
    """Tests for Activity CRUD functions (create, get, update, delete).

    Verifies AC2.1 and AC2.2.
    """

    @pytest.mark.asyncio
    async def test_create_get_update_delete(self) -> None:
        """Full CRUD lifecycle: create, get, update, delete.

        Verifies AC2.1.
        """
        from promptgrimoire.db.activities import (
            create_activity,
            delete_activity,
            get_activity,
            update_activity,
        )

        _, week = await _make_course_and_week("crud-life")

        # Create
        activity = await create_activity(
            week_id=week.id,
            title="Original Title",
            description="Original description",
        )
        assert isinstance(activity.id, UUID)
        assert activity.title == "Original Title"
        assert activity.description == "Original description"
        assert activity.template_workspace_id is not None

        # Verify template workspace back-link
        from promptgrimoire.db.workspaces import get_workspace

        template = await get_workspace(activity.template_workspace_id)
        assert template is not None
        assert template.activity_id == activity.id

        # Get
        fetched = await get_activity(activity.id)
        assert fetched is not None
        assert fetched.id == activity.id
        assert fetched.title == "Original Title"
        assert fetched.description == "Original description"

        # Update title and description
        updated = await update_activity(
            activity.id,
            title="Updated Title",
            description="Updated description",
        )
        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.description == "Updated description"
        assert updated.updated_at > activity.updated_at

        # Get again to verify persistence
        refetched = await get_activity(activity.id)
        assert refetched is not None
        assert refetched.title == "Updated Title"

        # Delete
        deleted = await delete_activity(activity.id)
        assert deleted is True

        # Verify gone
        gone = await get_activity(activity.id)
        assert gone is None

    @pytest.mark.asyncio
    async def test_delete_cascades_template_workspace(self) -> None:
        """Deleting Activity also deletes its template workspace.

        Verifies AC2.2.
        """
        from promptgrimoire.db.activities import create_activity, delete_activity
        from promptgrimoire.db.workspaces import get_workspace

        _, week = await _make_course_and_week("crud-cascade")

        activity = await create_activity(week_id=week.id, title="Cascade Test")
        template_id = activity.template_workspace_id

        # Template workspace exists
        assert await get_workspace(template_id) is not None

        # Delete activity
        await delete_activity(activity.id)

        # Template workspace is also gone
        assert await get_workspace(template_id) is None

    @pytest.mark.asyncio
    async def test_update_clear_description(self) -> None:
        """Setting description=None clears it."""
        from promptgrimoire.db.activities import (
            create_activity,
            get_activity,
            update_activity,
        )

        _, week = await _make_course_and_week("crud-clear")

        activity = await create_activity(
            week_id=week.id,
            title="Has Desc",
            description="Will be cleared",
        )
        assert activity.description == "Will be cleared"

        updated = await update_activity(activity.id, description=None)
        assert updated is not None
        assert updated.description is None

        refetched = await get_activity(activity.id)
        assert refetched is not None
        assert refetched.description is None

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self) -> None:
        """Updating a non-existent activity returns None."""
        from promptgrimoire.db.activities import update_activity

        result = await update_activity(uuid4(), title="Nope")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self) -> None:
        """Deleting a non-existent activity returns False."""
        from promptgrimoire.db.activities import delete_activity

        result = await delete_activity(uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self) -> None:
        """Getting a non-existent activity returns None."""
        from promptgrimoire.db.activities import get_activity

        result = await get_activity(uuid4())
        assert result is None


class TestListActivities:
    """Tests for list_activities_for_week and list_activities_for_course.

    Verifies AC2.3 and AC2.4.
    """

    @pytest.mark.asyncio
    async def test_list_for_week_ordered_by_created_at(self) -> None:
        """Activities listed for a week are ordered by created_at.

        Verifies AC2.3.
        """
        from promptgrimoire.db.activities import (
            create_activity,
            list_activities_for_week,
        )

        _, week = await _make_course_and_week("list-week")

        # Create 3 activities -- sequential creates ensure distinct created_at
        await create_activity(week_id=week.id, title="First")
        await create_activity(week_id=week.id, title="Second")
        await create_activity(week_id=week.id, title="Third")

        activities = await list_activities_for_week(week.id)

        assert len(activities) >= 3
        titles = [a.title for a in activities]
        assert titles.index("First") < titles.index("Second") < titles.index("Third")

    @pytest.mark.asyncio
    async def test_list_for_week_empty(self) -> None:
        """Returns empty list for a week with no activities."""
        from promptgrimoire.db.activities import list_activities_for_week

        _, week = await _make_course_and_week("list-empty")

        activities = await list_activities_for_week(week.id)
        assert activities == []

    @pytest.mark.asyncio
    async def test_list_for_course_across_weeks(self) -> None:
        """Activities for a course span all weeks, ordered by week then created_at.

        Verifies AC2.4.
        """
        from promptgrimoire.db.activities import (
            create_activity,
            list_activities_for_course,
        )
        from promptgrimoire.db.courses import create_course
        from promptgrimoire.db.weeks import create_week

        code = f"T{uuid4().hex[:6].upper()}"
        course = await create_course(code=code, name="Multi-Week", semester="2026-S1")
        week1 = await create_week(course_id=course.id, week_number=1, title="Week 1")
        week2 = await create_week(course_id=course.id, week_number=2, title="Week 2")

        # Activities in week 2 created first, but should appear after week 1's
        await create_activity(week_id=week2.id, title="W2-First")
        await create_activity(week_id=week1.id, title="W1-First")
        await create_activity(week_id=week1.id, title="W1-Second")

        activities = await list_activities_for_course(course.id)

        assert len(activities) >= 3
        titles = [a.title for a in activities]
        # Week 1 activities should come before Week 2
        assert titles.index("W1-First") < titles.index("W2-First")
        assert titles.index("W1-Second") < titles.index("W2-First")
        # Within week 1, ordered by created_at
        assert titles.index("W1-First") < titles.index("W1-Second")
