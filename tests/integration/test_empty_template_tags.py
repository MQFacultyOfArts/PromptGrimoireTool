"""Integration tests for tag management on empty template workspaces.

Tests verify the data-layer contracts for tag CRUD, import, and cloning
on workspaces with zero WorkspaceDocument rows. These serve as a safety
net for the UI change that adds the tag toolbar to the empty-document
branch of the annotation page.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Traceability:
- Design: docs/implementation-plans/2026-03-02-tags-214/phase_01.md Task 1
- AC: tags-214.AC1.1, AC1.3, AC1.4, AC2.1, AC3.1
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_week_activity() -> tuple:
    """Create a Course, Week, and Activity for tag tests.

    Returns (Course, Activity). The Activity's template workspace
    is automatically created by create_activity() and back-linked.
    """
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="EmptyTagTest", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Empty Template Activity")
    return course, activity


class TestEmptyWorkspaceTags:
    """Verify workspace_tags() works for workspaces with zero documents (AC1.1)."""

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_empty_tag_list(self) -> None:
        """workspace_tags() returns empty list for a new workspace with no tags."""
        from promptgrimoire.pages.annotation.tags import workspace_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        result = await workspace_tags(ws_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_tags_on_empty_workspace_are_retrievable(self) -> None:
        """Tags on a workspace with zero documents are returned.

        Verifies workspace_tags() returns tags created on a workspace
        that has no WorkspaceDocument rows.
        """
        from promptgrimoire.db.tags import create_tag, create_tag_group
        from promptgrimoire.pages.annotation.tags import TagInfo, workspace_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="Legal Issues")
        tag = await create_tag(
            ws_id, name="Jurisdiction", color="#1f77b4", group_id=group.id
        )

        result = await workspace_tags(ws_id)

        assert len(result) == 1
        ti = result[0]
        assert isinstance(ti, TagInfo)
        assert ti.name == "Jurisdiction"
        assert ti.colour == "#1f77b4"
        assert ti.raw_key == str(tag.id)
        assert ti.group_name == "Legal Issues"


class TestImportTagsToEmptyTemplate:
    """Verify import_tags_from_activity() works for empty templates (AC1.3)."""

    @pytest.mark.asyncio
    async def test_import_tags_into_empty_template(self) -> None:
        """Imported tags appear on an empty template.

        Tags imported from another activity via
        import_tags_from_activity() are returned by workspace_tags().
        """
        from promptgrimoire.db.tags import create_tag, import_tags_from_activity
        from promptgrimoire.pages.annotation.tags import workspace_tags

        # Source activity with tags
        _, source_activity = await _make_course_week_activity()
        source_ws = source_activity.template_workspace_id
        await create_tag(source_ws, name="Damages", color="#d62728")
        await create_tag(source_ws, name="Liability", color="#2ca02c")

        # Target activity (empty template, different course)
        _, target_activity = await _make_course_week_activity()
        target_ws = target_activity.template_workspace_id

        # Verify target starts empty
        assert await workspace_tags(target_ws) == []

        # Import
        imported = await import_tags_from_activity(
            source_activity_id=source_activity.id,
            target_workspace_id=target_ws,
        )

        assert len(imported) == 2

        # Verify imported tags appear in workspace_tags
        result = await workspace_tags(target_ws)
        assert len(result) == 2
        names = {ti.name for ti in result}
        assert names == {"Damages", "Liability"}

    @pytest.mark.asyncio
    async def test_import_tags_with_groups_into_empty_template(self) -> None:
        """Tags imported with groups preserve group assignment on the empty target."""
        from promptgrimoire.db.tags import (
            create_tag,
            create_tag_group,
            import_tags_from_activity,
        )
        from promptgrimoire.pages.annotation.tags import workspace_tags

        # Source with grouped tag
        _, source_activity = await _make_course_week_activity()
        source_ws = source_activity.template_workspace_id
        group = await create_tag_group(source_ws, name="Core Issues")
        await create_tag(
            source_ws, name="Negligence", color="#ff7f0e", group_id=group.id
        )

        # Empty target
        _, target_activity = await _make_course_week_activity()
        target_ws = target_activity.template_workspace_id

        await import_tags_from_activity(
            source_activity_id=source_activity.id,
            target_workspace_id=target_ws,
        )

        result = await workspace_tags(target_ws)
        assert len(result) == 1
        assert result[0].name == "Negligence"
        assert result[0].group_name == "Core Issues"


class TestTagMutationsReflectedInWorkspaceTags:
    """Verify workspace_tags() reflects mutations after each change (AC1.4)."""

    @pytest.mark.asyncio
    async def test_create_then_query(self) -> None:
        """Creating a new tag is immediately reflected in workspace_tags()."""
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.pages.annotation.tags import workspace_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        # Start empty
        assert await workspace_tags(ws_id) == []

        # Create
        await create_tag(ws_id, name="Tag A", color="#1f77b4")
        result = await workspace_tags(ws_id)
        assert len(result) == 1
        assert result[0].name == "Tag A"

    @pytest.mark.asyncio
    async def test_rename_then_query(self) -> None:
        """Renaming a tag is reflected in the next workspace_tags() call."""
        from promptgrimoire.db.tags import create_tag, update_tag
        from promptgrimoire.pages.annotation.tags import workspace_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="Old Name", color="#ff7f0e")

        # Rename
        await update_tag(tag.id, name="New Name")

        result = await workspace_tags(ws_id)
        assert len(result) == 1
        assert result[0].name == "New Name"

    @pytest.mark.asyncio
    async def test_delete_then_query(self) -> None:
        """Deleting a tag removes it from workspace_tags()."""
        from promptgrimoire.db.tags import create_tag, delete_tag
        from promptgrimoire.pages.annotation.tags import workspace_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="To Delete", color="#d62728")
        assert len(await workspace_tags(ws_id)) == 1

        await delete_tag(tag.id)

        result = await workspace_tags(ws_id)
        assert result == []

    @pytest.mark.asyncio
    async def test_sequential_mutations(self) -> None:
        """A sequence of create, rename, and delete mutations are all reflected."""
        from promptgrimoire.db.tags import create_tag, delete_tag, update_tag
        from promptgrimoire.pages.annotation.tags import workspace_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        # Create two tags
        tag_a = await create_tag(ws_id, name="Alpha", color="#1f77b4")
        tag_b = await create_tag(ws_id, name="Beta", color="#ff7f0e")
        result = await workspace_tags(ws_id)
        assert len(result) == 2
        assert {ti.name for ti in result} == {"Alpha", "Beta"}

        # Rename Alpha
        await update_tag(tag_a.id, name="Alpha Renamed")
        result = await workspace_tags(ws_id)
        assert {ti.name for ti in result} == {"Alpha Renamed", "Beta"}

        # Delete Beta
        await delete_tag(tag_b.id)
        result = await workspace_tags(ws_id)
        assert len(result) == 1
        assert result[0].name == "Alpha Renamed"

        # Create a third tag
        await create_tag(ws_id, name="Gamma", color="#2ca02c")
        result = await workspace_tags(ws_id)
        assert len(result) == 2
        assert {ti.name for ti in result} == {"Alpha Renamed", "Gamma"}


class TestCloneEmptyTemplateWithTags:
    """Verify cloning copies tags from empty templates (AC2.1)."""

    @pytest.mark.asyncio
    async def test_clone_copies_tags_from_empty_template(self) -> None:
        """Tags and groups on an empty template are cloned.

        clone_workspace_from_activity() snapshot-copies tags and
        groups to the new student workspace.
        """
        from promptgrimoire.db.tags import create_tag, create_tag_group
        from promptgrimoire.db.workspaces import clone_workspace_from_activity
        from promptgrimoire.pages.annotation.tags import workspace_tags

        _, activity = await _make_course_week_activity()
        template_ws_id = activity.template_workspace_id

        # Configure tags on empty template
        group = await create_tag_group(template_ws_id, name="Issues")
        await create_tag(
            template_ws_id,
            name="Causation",
            color="#9467bd",
            group_id=group.id,
        )
        await create_tag(
            template_ws_id,
            name="Duty of Care",
            color="#8c564b",
            group_id=group.id,
        )

        # Clone (requires a real user for ACL FK constraint)
        from promptgrimoire.db.users import create_user

        user = await create_user(
            email=f"clone-{uuid4().hex[:8]}@test.local",
            display_name="Clone Tester",
        )
        clone, _doc_id_map = await clone_workspace_from_activity(
            activity_id=activity.id,
            user_id=user.id,
        )

        # Verify cloned workspace has the same tags
        template_tags = await workspace_tags(template_ws_id)
        clone_tags = await workspace_tags(clone.id)

        assert len(clone_tags) == len(template_tags)
        assert len(clone_tags) == 2

        template_names = {ti.name for ti in template_tags}
        clone_names = {ti.name for ti in clone_tags}
        assert clone_names == template_names

        # Verify group assignment preserved
        for ti in clone_tags:
            assert ti.group_name == "Issues"

        # Verify cloned tags have different UUIDs (independent copies)
        template_keys = {ti.raw_key for ti in template_tags}
        clone_keys = {ti.raw_key for ti in clone_tags}
        assert template_keys.isdisjoint(clone_keys)


class TestWorkspaceWithDocumentsStillReturnsTags:
    """Tags return identically with documents present (AC3.1)."""

    @pytest.mark.asyncio
    async def test_tags_returned_with_document_present(self) -> None:
        """workspace_tags() returns tags the same way whether documents exist or not."""
        from promptgrimoire.db.tags import create_tag, create_tag_group
        from promptgrimoire.db.workspace_documents import add_document
        from promptgrimoire.pages.annotation.tags import TagInfo, workspace_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        # Add a document
        await add_document(
            workspace_id=ws_id,
            type="source",
            content="<p><span>Hello world</span></p>",
            source_type="text",
            title="Test Document",
        )

        # Add tags
        group = await create_tag_group(ws_id, name="Analysis")
        tag = await create_tag(
            ws_id, name="Key Finding", color="#e377c2", group_id=group.id
        )

        result = await workspace_tags(ws_id)

        assert len(result) == 1
        ti = result[0]
        assert isinstance(ti, TagInfo)
        assert ti.name == "Key Finding"
        assert ti.colour == "#e377c2"
        assert ti.raw_key == str(tag.id)
        assert ti.group_name == "Analysis"
