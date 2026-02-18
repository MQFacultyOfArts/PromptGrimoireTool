"""Integration tests for tag management workflow.

Tests verify the combined workflow that Phase 5 wires together —
creating/importing tags and verifying they appear in the rendering
pipeline via workspace_tags(). Also tests creation permission gating
and delete-with-CRDT-cleanup integration.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Traceability:
- Design: docs/implementation-plans/2026-02-18-95-annotation-tags/phase_05.md Task 6
- AC: 95-annotation-tags.AC6.2, AC6.3, AC7.5, AC7.7
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_week_activity(
    *,
    default_allow_tag_creation: bool = True,
    allow_tag_creation: bool | None = None,
) -> tuple:
    """Create a Course, Week, and Activity for tag management tests.

    Returns (Course, Activity). The Activity's template workspace
    is automatically created by create_activity() and back-linked.
    """
    from promptgrimoire.db.activities import create_activity, update_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Course
    from promptgrimoire.db.weeks import create_week

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="MgmtTest", semester="2026-S1")

    if not default_allow_tag_creation:
        async with get_session() as session:
            c = await session.get(Course, course.id)
            assert c is not None
            c.default_allow_tag_creation = default_allow_tag_creation
            session.add(c)
            await session.flush()
            await session.refresh(c)
            course = c

    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Mgmt Activity")

    if allow_tag_creation is not None:
        updated = await update_activity(
            activity.id, allow_tag_creation=allow_tag_creation
        )
        assert updated is not None
        activity = updated

    return course, activity


class TestQuickCreateWorkflow:
    """Verify the create-tag + workspace_tags rendering pipeline (AC6.2)."""

    @pytest.mark.asyncio
    async def test_created_tag_appears_in_workspace_tags(self) -> None:
        """Created tag appears in workspace_tags() with correct fields."""
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.pages.annotation.tags import TagInfo, workspace_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        new_tag = await create_tag(ws_id, name="Workflow Tag", color="#d62728")

        result = await workspace_tags(ws_id)
        assert len(result) == 1
        ti = result[0]
        assert isinstance(ti, TagInfo)
        assert ti.name == "Workflow Tag"
        assert ti.colour == "#d62728"
        assert ti.raw_key == str(new_tag.id)

    @pytest.mark.asyncio
    async def test_tag_uuid_usable_as_crdt_highlight_tag(self) -> None:
        """A created tag's UUID can be used as a CRDT highlight tag value."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag
        from promptgrimoire.pages.annotation.tags import workspace_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        new_tag = await create_tag(ws_id, name="CRDT Tag", color="#1f77b4")

        result = await workspace_tags(ws_id)
        raw_key = result[0].raw_key

        doc = AnnotationDocument(f"test-mgmt-{uuid4().hex[:8]}")
        hl_id = doc.add_highlight(0, 10, raw_key, "test text", "Author")

        highlights = doc.get_all_highlights()
        assert len(highlights) == 1
        assert highlights[0]["tag"] == str(new_tag.id)
        assert highlights[0]["id"] == hl_id


class TestCreationGating:
    """Verify permission enforcement on tag creation (AC6.3)."""

    @pytest.mark.asyncio
    async def test_creation_denied_when_course_disallows(self) -> None:
        """create_tag raises PermissionError when course default is False."""
        from promptgrimoire.db.tags import create_tag

        _, activity = await _make_course_week_activity(
            default_allow_tag_creation=False,
        )
        ws_id = activity.template_workspace_id

        with pytest.raises(PermissionError):
            await create_tag(ws_id, name="Denied", color="#ff0000")

    @pytest.mark.asyncio
    async def test_creation_allowed_when_course_allows(self) -> None:
        """create_tag succeeds when course default allows creation."""
        from promptgrimoire.db.tags import create_tag

        _, activity = await _make_course_week_activity(
            default_allow_tag_creation=True,
        )
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="Allowed", color="#00ff00")
        assert isinstance(tag.id, UUID)
        assert tag.name == "Allowed"


class TestDeleteWithCrdtCleanup:
    """Verify tag deletion removes CRDT highlights (AC7.5)."""

    @pytest.mark.asyncio
    async def test_delete_tag_removes_from_workspace_tags(self) -> None:
        """After delete_tag, workspace_tags() no longer includes the tag."""
        from promptgrimoire.db.tags import create_tag, delete_tag
        from promptgrimoire.pages.annotation.tags import workspace_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="To Delete", color="#ff7f0e")
        assert len(await workspace_tags(ws_id)) == 1

        await delete_tag(tag.id)

        result = await workspace_tags(ws_id)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_delete_tag_cleans_crdt_highlights(self) -> None:
        """delete_tag removes CRDT highlights referencing the deleted tag."""
        from promptgrimoire.crdt.annotation_doc import AnnotationDocument
        from promptgrimoire.db.tags import create_tag, delete_tag
        from promptgrimoire.db.workspaces import (
            get_workspace,
            save_workspace_crdt_state,
        )

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag = await create_tag(ws_id, name="CRDT Delete", color="#9467bd")
        tag_key = str(tag.id)

        # Build CRDT state with 2 highlights referencing this tag
        doc = AnnotationDocument("test-mgmt-crdt")
        doc.add_highlight(0, 10, tag_key, "first highlight", "Author")
        doc.add_highlight(10, 20, tag_key, "second highlight", "Author")
        await save_workspace_crdt_state(ws_id, doc.get_full_state())

        # Verify highlights exist before deletion
        assert len(doc.get_all_highlights()) == 2

        # Delete the tag (should clean up CRDT)
        await delete_tag(tag.id)

        # Reload CRDT and verify highlights are removed
        ws_after = await get_workspace(ws_id)
        assert ws_after is not None
        assert ws_after.crdt_state is not None
        doc_after = AnnotationDocument("verify")
        doc_after.apply_update(ws_after.crdt_state)
        tagged_after = [
            h for h in doc_after.get_all_highlights() if h["tag"] == tag_key
        ]
        assert len(tagged_after) == 0


class TestImportWorkflow:
    """Verify import_tags_from_activity pipeline (AC7.7)."""

    @pytest.mark.asyncio
    async def test_imported_tags_appear_in_workspace_tags(self) -> None:
        """Tags imported from another activity appear in workspace_tags()."""
        from promptgrimoire.db.tags import create_tag, import_tags_from_activity
        from promptgrimoire.pages.annotation.tags import workspace_tags

        # Source activity with 2 tags
        _, source_activity = await _make_course_week_activity()
        source_ws = source_activity.template_workspace_id
        await create_tag(source_ws, name="Tag A", color="#1f77b4")
        await create_tag(source_ws, name="Tag B", color="#ff7f0e")

        # Target activity (separate course to ensure independence)
        _, target_activity = await _make_course_week_activity()
        target_ws = target_activity.template_workspace_id

        # Verify target starts empty
        assert len(await workspace_tags(target_ws)) == 0

        # Import
        imported = await import_tags_from_activity(
            source_activity_id=source_activity.id,
            target_workspace_id=target_ws,
        )

        assert len(imported) == 2

        # Verify they appear in workspace_tags with correct names/colours
        result = await workspace_tags(target_ws)
        assert len(result) == 2
        names = {ti.name for ti in result}
        assert names == {"Tag A", "Tag B"}
        colours = {ti.colour for ti in result}
        assert "#1f77b4" in colours
        assert "#ff7f0e" in colours

    @pytest.mark.asyncio
    async def test_imported_tags_have_different_uuids(self) -> None:
        """Imported tags get new UUIDs (independent copies, not references)."""
        from promptgrimoire.db.tags import create_tag, import_tags_from_activity
        from promptgrimoire.pages.annotation.tags import workspace_tags

        _, source_activity = await _make_course_week_activity()
        source_ws = source_activity.template_workspace_id
        await create_tag(source_ws, name="Original", color="#2ca02c")

        source_tags = await workspace_tags(source_ws)
        source_key = source_tags[0].raw_key

        _, target_activity = await _make_course_week_activity()
        target_ws = target_activity.template_workspace_id

        await import_tags_from_activity(
            source_activity_id=source_activity.id,
            target_workspace_id=target_ws,
        )

        target_tags = await workspace_tags(target_ws)
        assert len(target_tags) == 1
        assert target_tags[0].raw_key != source_key
        assert target_tags[0].name == "Original"
        assert target_tags[0].colour == "#2ca02c"
