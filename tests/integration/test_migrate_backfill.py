"""Integration tests for the backfill-tags migration command.

These tests verify that ``_backfill_tags()`` correctly hydrates CRDT state
from DB tags, is idempotent, detects drift, and supports single-workspace
filtering.

Requires a running PostgreSQL instance.  Set DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _make_course_week_activity() -> tuple:
    """Create Course -> Week -> Activity with a template workspace.

    Returns (Course, Activity) where Activity.template_workspace_id is set.
    """
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="BackfillTest", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Backfill Activity")
    return course, activity


def _load_crdt(crdt_state: bytes | None) -> tuple[dict, dict]:
    """Load CRDT state bytes into an AnnotationDocument and return tags/groups."""
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument

    doc = AnnotationDocument("verify")
    if crdt_state:
        doc.apply_update(crdt_state)
    return doc.list_tags(), doc.list_tag_groups()


async def _get_workspace_crdt_state(ws_id: UUID) -> bytes | None:
    """Fetch the workspace's crdt_state from DB."""
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Workspace

    async with get_session() as session:
        ws = await session.get(Workspace, ws_id)
        assert ws is not None
        return ws.crdt_state


class TestBackfillEmptyHydration:
    """Verify backfill populates CRDT when crdt_state is empty."""

    @pytest.mark.asyncio
    async def test_hydrates_tags_and_groups_into_empty_crdt(self) -> None:
        """Create tags in DB with no CRDT state.  Backfill should hydrate."""
        from promptgrimoire.cli.migrate import _backfill_tags
        from promptgrimoire.db.tags import create_tag, create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="Evidence")
        tag1 = await create_tag(
            ws_id, name="Jurisdiction", color="#1f77b4", group_id=group.id
        )
        tag2 = await create_tag(ws_id, name="Remedy", color="#ff7f0e")

        # Confirm CRDT is empty before backfill
        crdt_state = await _get_workspace_crdt_state(ws_id)
        tags_before, groups_before = _load_crdt(crdt_state)
        assert not tags_before
        assert not groups_before

        await _backfill_tags(fix=True, single_workspace_id=str(ws_id))

        # Verify CRDT now has the tags and group
        crdt_state = await _get_workspace_crdt_state(ws_id)
        tags_after, groups_after = _load_crdt(crdt_state)

        assert str(tag1.id) in tags_after
        assert str(tag2.id) in tags_after
        assert str(group.id) in groups_after

        # Verify tag data
        t1 = tags_after[str(tag1.id)]
        assert t1["name"] == "Jurisdiction"
        assert t1["colour"] == "#1f77b4"
        assert t1["group_id"] == str(group.id)

        t2 = tags_after[str(tag2.id)]
        assert t2["name"] == "Remedy"
        assert t2["colour"] == "#ff7f0e"
        assert t2["group_id"] is None

        # Verify group data
        g = groups_after[str(group.id)]
        assert g["name"] == "Evidence"


class TestBackfillIdempotency:
    """Verify running backfill twice yields same logical state."""

    @pytest.mark.asyncio
    async def test_second_run_reports_no_changes(self) -> None:
        """Run backfill twice; second run should find everything OK."""
        from promptgrimoire.cli.migrate import _backfill_tags
        from promptgrimoire.db.tags import create_tag, create_tag_group

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        group = await create_tag_group(ws_id, name="Analysis")
        await create_tag(ws_id, name="Issue", color="#2ca02c", group_id=group.id)

        # First run: hydrates
        await _backfill_tags(fix=True, single_workspace_id=str(ws_id))
        crdt_state_1 = await _get_workspace_crdt_state(ws_id)
        tags_1, groups_1 = _load_crdt(crdt_state_1)

        # Second run: should be idempotent
        await _backfill_tags(fix=True, single_workspace_id=str(ws_id))
        crdt_state_2 = await _get_workspace_crdt_state(ws_id)
        tags_2, groups_2 = _load_crdt(crdt_state_2)

        # Compare logical equality (not byte-identical due to CRDT non-determinism)
        assert tags_1.keys() == tags_2.keys()
        assert groups_1.keys() == groups_2.keys()

        for tag_id in tags_1:
            assert tags_1[tag_id]["name"] == tags_2[tag_id]["name"]
            assert tags_1[tag_id]["colour"] == tags_2[tag_id]["colour"]
            assert tags_1[tag_id]["group_id"] == tags_2[tag_id]["group_id"]

        for group_id in groups_1:
            assert groups_1[group_id]["name"] == groups_2[group_id]["name"]


class TestBackfillDriftDetection:
    """Verify drift detection when DB and CRDT diverge."""

    @pytest.mark.asyncio
    async def test_detects_and_fixes_drift(self) -> None:
        """Add a tag to DB after initial backfill.  Verify drift detected and fixed."""
        from promptgrimoire.cli.migrate import _backfill_tags
        from promptgrimoire.db.tags import create_tag

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        tag1 = await create_tag(ws_id, name="Original", color="#1f77b4")

        # Initial backfill
        await _backfill_tags(fix=True, single_workspace_id=str(ws_id))

        crdt_state = await _get_workspace_crdt_state(ws_id)
        tags, _ = _load_crdt(crdt_state)
        assert str(tag1.id) in tags

        # Add a new tag to DB without updating CRDT
        tag2 = await create_tag(ws_id, name="NewTag", color="#ff7f0e")

        # Verify-only mode: drift reported but not fixed
        await _backfill_tags(fix=False, single_workspace_id=str(ws_id))
        crdt_state = await _get_workspace_crdt_state(ws_id)
        tags_verify, _ = _load_crdt(crdt_state)
        assert str(tag2.id) not in tags_verify  # Not fixed yet

        # Fix mode: drift resolved
        await _backfill_tags(fix=True, single_workspace_id=str(ws_id))
        crdt_state = await _get_workspace_crdt_state(ws_id)
        tags_fixed, _ = _load_crdt(crdt_state)
        assert str(tag2.id) in tags_fixed
        assert tags_fixed[str(tag2.id)]["name"] == "NewTag"


class TestBackfillSingleWorkspaceFilter:
    """Verify single_workspace_id filters to one workspace only."""

    @pytest.mark.asyncio
    async def test_only_processes_specified_workspace(self) -> None:
        """Create two workspaces; filter to one.  Only that one gets backfilled."""
        from promptgrimoire.cli.migrate import _backfill_tags
        from promptgrimoire.db.tags import create_tag

        _, activity1 = await _make_course_week_activity()
        ws1_id = activity1.template_workspace_id

        _, activity2 = await _make_course_week_activity()
        ws2_id = activity2.template_workspace_id

        await create_tag(ws1_id, name="TagWS1", color="#1f77b4")
        await create_tag(ws2_id, name="TagWS2", color="#ff7f0e")

        # Only backfill ws1
        await _backfill_tags(fix=True, single_workspace_id=str(ws1_id))

        # ws1 should be hydrated
        crdt_1 = await _get_workspace_crdt_state(ws1_id)
        tags_1, _ = _load_crdt(crdt_1)
        assert len(tags_1) == 1

        # ws2 should still be empty
        crdt_2 = await _get_workspace_crdt_state(ws2_id)
        tags_2, _ = _load_crdt(crdt_2)
        assert len(tags_2) == 0


class TestBackfillNoTags:
    """Verify workspace with no tags is skipped."""

    @pytest.mark.asyncio
    async def test_workspace_without_tags_not_processed(self) -> None:
        """Create a workspace with no tags.  Backfill should skip it."""
        from promptgrimoire.cli.migrate import _backfill_tags

        _, activity = await _make_course_week_activity()
        ws_id = activity.template_workspace_id

        # Run backfill -- should print "No workspaces with tags found" or skip
        await _backfill_tags(fix=True, single_workspace_id=str(ws_id))

        # CRDT should remain empty
        crdt_state = await _get_workspace_crdt_state(ws_id)
        tags, groups = _load_crdt(crdt_state)
        assert not tags
        assert not groups
