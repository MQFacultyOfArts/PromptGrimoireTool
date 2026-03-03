"""Tests for delete guard logic (student workspace protection).

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify has_student_workspaces() count accuracy, which is the
foundation for all delete guard logic in activities, weeks, and courses.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_and_week(suffix: str = "") -> tuple[UUID, UUID]:
    """Create a course and week, returning (course_id, week_id)."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name=f"Test{suffix}", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course.id, week.id


async def _make_activity(week_id: UUID, title: str = "Test Activity") -> UUID:
    """Create an activity with template workspace, returning activity_id."""
    from promptgrimoire.db.activities import create_activity

    activity = await create_activity(week_id=week_id, title=title)
    return activity.id


async def _create_student() -> UUID:
    """Create a real user in the DB and return user_id."""
    from promptgrimoire.db.users import create_user

    tag = uuid4().hex[:8]
    user = await create_user(
        email=f"student-{tag}@test.local",
        display_name=f"Student {tag}",
    )
    return user.id


async def _clone_for_student(activity_id: UUID) -> UUID:
    """Clone activity template for a new student, returning workspace_id."""
    from promptgrimoire.db.workspaces import clone_workspace_from_activity

    user_id = await _create_student()
    workspace, _doc_map = await clone_workspace_from_activity(activity_id, user_id)
    return workspace.id


class TestHasStudentWorkspaces:
    """Tests for has_student_workspaces() count accuracy."""

    @pytest.mark.asyncio
    async def test_returns_zero_for_activity_with_no_students(self) -> None:
        """Activity with only template workspace returns 0."""
        from promptgrimoire.db.workspaces import has_student_workspaces

        _course_id, week_id = await _make_course_and_week("no-students")
        activity_id = await _make_activity(week_id)

        count = await has_student_workspaces(activity_id)
        assert count == 0

    @pytest.mark.asyncio
    async def test_returns_one_after_single_clone(self) -> None:
        """Activity with one student clone returns 1."""
        from promptgrimoire.db.workspaces import has_student_workspaces

        _course_id, week_id = await _make_course_and_week("one-student")
        activity_id = await _make_activity(week_id)
        await _clone_for_student(activity_id)

        count = await has_student_workspaces(activity_id)
        assert count == 1

    @pytest.mark.asyncio
    async def test_returns_two_after_two_clones(self) -> None:
        """Activity with two student clones returns 2."""
        from promptgrimoire.db.workspaces import has_student_workspaces

        _course_id, week_id = await _make_course_and_week("two-students")
        activity_id = await _make_activity(week_id)
        await _clone_for_student(activity_id)
        await _clone_for_student(activity_id)

        count = await has_student_workspaces(activity_id)
        assert count == 2


class TestDeleteActivity:
    """Tests for delete_activity() with force parameter and guard logic."""

    @pytest.mark.asyncio
    async def test_deletes_activity_with_no_students(self) -> None:
        """Activity with no student workspaces deletes (force=False).

        Verifies crud-management-229.AC2.2: Activity and its template
        workspace should be removed.
        """
        from promptgrimoire.db.activities import delete_activity, get_activity
        from promptgrimoire.db.workspaces import get_workspace

        _course_id, week_id = await _make_course_and_week("del-act-no-stu")
        activity_id = await _make_activity(week_id)

        # Get template workspace id before deletion
        activity = await get_activity(activity_id)
        assert activity is not None
        template_ws_id = activity.template_workspace_id

        result = await delete_activity(activity_id)
        assert result is True

        # Activity gone
        assert await get_activity(activity_id) is None
        # Template workspace gone
        assert await get_workspace(template_ws_id) is None

    @pytest.mark.asyncio
    async def test_blocked_when_student_workspaces_exist(self) -> None:
        """Delete blocked when student workspaces exist.

        Verifies crud-management-229.AC2.3: DeletionBlockedError
        raised with correct count when force=False.
        """
        from promptgrimoire.db.activities import delete_activity
        from promptgrimoire.db.exceptions import DeletionBlockedError

        _course_id, week_id = await _make_course_and_week("del-act-blocked")
        activity_id = await _make_activity(week_id)
        await _clone_for_student(activity_id)
        await _clone_for_student(activity_id)

        with pytest.raises(DeletionBlockedError) as exc_info:
            await delete_activity(activity_id)

        assert exc_info.value.student_workspace_count == 2

    @pytest.mark.asyncio
    async def test_force_deletes_with_student_workspaces(self) -> None:
        """force=True deletes activity even with student workspaces."""
        from promptgrimoire.db.activities import delete_activity, get_activity
        from promptgrimoire.db.workspaces import get_workspace

        _course_id, week_id = await _make_course_and_week("del-act-force")
        activity_id = await _make_activity(week_id)
        student_ws_id = await _clone_for_student(activity_id)

        activity = await get_activity(activity_id)
        assert activity is not None
        template_ws_id = activity.template_workspace_id

        result = await delete_activity(activity_id, force=True)
        assert result is True

        # Activity gone
        assert await get_activity(activity_id) is None
        # Template workspace gone
        assert await get_workspace(template_ws_id) is None
        # Student workspace gone
        assert await get_workspace(student_ws_id) is None

    @pytest.mark.asyncio
    async def test_nonexistent_activity_returns_false(self) -> None:
        """Nonexistent ID returns False regardless of force."""
        from promptgrimoire.db.activities import delete_activity

        result = await delete_activity(uuid4())
        assert result is False

        result_force = await delete_activity(uuid4(), force=True)
        assert result_force is False


class TestDeleteWeek:
    """Tests for delete_week() with force parameter and guard logic."""

    @pytest.mark.asyncio
    async def test_deletes_week_with_no_students(self) -> None:
        """Week with no student workspaces deletes (force=False).

        Verifies crud-management-229.AC2.1: Week and its activities
        are removed.
        """
        from promptgrimoire.db.activities import get_activity
        from promptgrimoire.db.weeks import delete_week, get_week_by_id

        _course_id, week_id = await _make_course_and_week("del-wk-no-stu")
        act_id = await _make_activity(week_id, "Act 1")

        result = await delete_week(week_id)
        assert result is True

        # Week gone
        assert await get_week_by_id(week_id) is None
        # Activity gone (CASCADE)
        assert await get_activity(act_id) is None

    @pytest.mark.asyncio
    async def test_blocked_when_student_workspaces_exist(
        self,
    ) -> None:
        """Delete blocked with aggregate count across activities.

        Verifies crud-management-229.AC2.3: DeletionBlockedError
        raised with total student workspace count.
        """
        from promptgrimoire.db.exceptions import DeletionBlockedError
        from promptgrimoire.db.weeks import delete_week

        _course_id, week_id = await _make_course_and_week("del-wk-blocked")
        act1_id = await _make_activity(week_id, "Act A")
        act2_id = await _make_activity(week_id, "Act B")
        await _clone_for_student(act1_id)
        await _clone_for_student(act1_id)
        await _clone_for_student(act2_id)

        with pytest.raises(DeletionBlockedError) as exc_info:
            await delete_week(week_id)

        # 2 from act1 + 1 from act2 = 3
        assert exc_info.value.student_workspace_count == 3

    @pytest.mark.asyncio
    async def test_force_deletes_with_student_workspaces(
        self,
    ) -> None:
        """force=True cascades through student workspaces.

        Verifies crud-management-229.AC2.4: Admin force-deletes a
        week with student workspaces; cascade removes all children.
        """
        from promptgrimoire.db.activities import get_activity
        from promptgrimoire.db.weeks import delete_week, get_week_by_id
        from promptgrimoire.db.workspaces import get_workspace

        _course_id, week_id = await _make_course_and_week("del-wk-force")
        act_id = await _make_activity(week_id, "Force Act")
        student_ws_id = await _clone_for_student(act_id)

        # Get template workspace id
        activity = await get_activity(act_id)
        assert activity is not None
        template_ws_id = activity.template_workspace_id

        result = await delete_week(week_id, force=True)
        assert result is True

        # Week gone
        assert await get_week_by_id(week_id) is None
        # Activity gone
        assert await get_activity(act_id) is None
        # Template workspace gone
        assert await get_workspace(template_ws_id) is None
        # Student workspace gone
        assert await get_workspace(student_ws_id) is None

    @pytest.mark.asyncio
    async def test_nonexistent_week_returns_false(self) -> None:
        """Nonexistent ID returns False regardless of force."""
        from promptgrimoire.db.weeks import delete_week

        result = await delete_week(uuid4())
        assert result is False

        result_force = await delete_week(uuid4(), force=True)
        assert result_force is False


class TestDeleteWorkspace:
    """Tests for delete_workspace() with ownership check."""

    @pytest.mark.asyncio
    async def test_owner_can_delete_workspace(self) -> None:
        """Owner user_id succeeds (workspace and documents deleted via CASCADE).

        Verifies crud-management-229.AC3.5 (success path): workspace owner
        can delete their own workspace.
        """
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            delete_workspace,
            get_workspace,
        )

        _course_id, week_id = await _make_course_and_week("del-ws-owner")
        activity_id = await _make_activity(week_id)
        user_id = await _create_student()

        workspace, _doc_map = await clone_workspace_from_activity(activity_id, user_id)

        await delete_workspace(workspace.id, user_id=user_id)

        # Workspace gone
        assert await get_workspace(workspace.id) is None

    @pytest.mark.asyncio
    async def test_non_owner_cannot_delete_workspace(self) -> None:
        """Non-owner user_id raises PermissionError.

        Verifies crud-management-229.AC3.5: DB-level delete_workspace()
        raises PermissionError when user_id is not workspace owner.
        """
        from promptgrimoire.db.workspaces import (
            clone_workspace_from_activity,
            delete_workspace,
        )

        _course_id, week_id = await _make_course_and_week("del-ws-non-owner")
        activity_id = await _make_activity(week_id)
        owner_id = await _create_student()
        other_id = await _create_student()

        workspace, _doc_map = await clone_workspace_from_activity(activity_id, owner_id)

        with pytest.raises(PermissionError, match="Only workspace owner can delete"):
            await delete_workspace(workspace.id, user_id=other_id)

    @pytest.mark.asyncio
    async def test_nonexistent_workspace_is_noop(self) -> None:
        """Deleting a nonexistent workspace does not raise."""
        from promptgrimoire.db.workspaces import delete_workspace

        user_id = await _create_student()
        # Should not raise — workspace does not exist
        await delete_workspace(uuid4(), user_id=user_id)


class TestDeleteDocument:
    """Tests for delete_document() with provenance guard."""

    @pytest.mark.asyncio
    async def test_deletes_user_uploaded_document(self) -> None:
        """User-uploaded document (source_document_id IS NULL) deletes.

        Verifies crud-management-229.AC4.1: Owner deletes a user-uploaded
        document; document and annotations removed.
        """
        from promptgrimoire.db.workspace_documents import (
            add_document,
            delete_document,
            get_document,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>User uploaded content</p>",
            source_type="html",
            title="My Upload",
        )
        assert doc.source_document_id is None

        result = await delete_document(doc.id)
        assert result is True

        # Document gone
        assert await get_document(doc.id) is None

    @pytest.mark.asyncio
    async def test_blocks_deletion_of_template_cloned_document(self) -> None:
        """Template-cloned document raises ProtectedDocumentError.

        Verifies crud-management-229.AC4.4: DB-level delete_document()
        raises ProtectedDocumentError for template-cloned documents.
        """
        from promptgrimoire.db.exceptions import ProtectedDocumentError
        from promptgrimoire.db.workspace_documents import (
            add_document,
            delete_document,
            list_documents,
        )
        from promptgrimoire.db.workspaces import clone_workspace_from_activity

        _course_id, week_id = await _make_course_and_week("del-doc-cloned")
        activity_id = await _make_activity(week_id)

        # Add a document to the template workspace
        from promptgrimoire.db.activities import get_activity

        activity = await get_activity(activity_id)
        assert activity is not None
        await add_document(
            workspace_id=activity.template_workspace_id,
            type="source",
            content="<p>Template document</p>",
            source_type="html",
            title="Template Doc",
        )

        # Clone for a student — cloned doc has source_document_id set
        user_id = await _create_student()
        clone, _doc_map = await clone_workspace_from_activity(activity_id, user_id)
        cloned_docs = await list_documents(clone.id)
        assert len(cloned_docs) == 1
        cloned_doc = cloned_docs[0]
        assert cloned_doc.source_document_id is not None

        with pytest.raises(ProtectedDocumentError) as exc_info:
            await delete_document(cloned_doc.id)

        assert exc_info.value.document_id == cloned_doc.id
        assert exc_info.value.source_document_id == cloned_doc.source_document_id

    @pytest.mark.asyncio
    async def test_tags_remain_after_document_deletion(self) -> None:
        """Workspace tags are preserved when a document is deleted.

        Tags belong to the workspace (TagGroup -> Workspace FK), not the
        document. Deleting a document must NOT cascade to tags.
        """
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.db.workspace_documents import (
            add_document,
            delete_document,
        )
        from promptgrimoire.db.workspaces import create_workspace

        workspace = await create_workspace()

        # Add a tag to the workspace
        tag = await create_tag(
            workspace_id=workspace.id,
            name="Important",
            color="#ff0000",
        )

        # Add a document
        doc = await add_document(
            workspace_id=workspace.id,
            type="source",
            content="<p>Content</p>",
            source_type="html",
        )

        # Delete the document
        result = await delete_document(doc.id)
        assert result is True

        # Tag still exists
        from promptgrimoire.db.tags import get_tag

        surviving_tag = await get_tag(tag.id)
        assert surviving_tag is not None
        assert surviving_tag.name == "Important"

    @pytest.mark.asyncio
    async def test_nonexistent_document_returns_false(self) -> None:
        """Nonexistent document_id returns False."""
        from promptgrimoire.db.workspace_documents import delete_document

        result = await delete_document(uuid4())
        assert result is False
