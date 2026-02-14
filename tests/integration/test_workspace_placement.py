"""Tests for workspace placement and listing operations.

These tests require a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Tests verify placing workspaces in Activities/Courses, making them loose,
listing by Activity/Course, and error handling for non-existent entities.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.db.models import Activity, Course, Week

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _setup_hierarchy() -> tuple[Course, Week, Activity]:
    """Create a full Course -> Week -> Activity hierarchy."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.weeks import create_week

    code = f"P{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="Placement Test", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Test Activity")
    return course, week, activity


class TestPlaceWorkspace:
    """Tests for workspace placement functions."""

    @pytest.mark.asyncio
    async def test_place_in_activity_sets_activity_id_clears_course_id(
        self,
    ) -> None:
        """Place in Activity: sets activity_id, clears course_id.

        Verifies AC3.1.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            place_workspace_in_activity,
            place_workspace_in_course,
        )

        course, _, activity = await _setup_hierarchy()
        ws = await create_workspace()

        # First place in course
        await place_workspace_in_course(ws.id, course.id)
        before = await get_workspace(ws.id)
        assert before is not None
        assert before.course_id == course.id
        original_updated_at = before.updated_at

        # Now place in activity -- should clear course_id
        result = await place_workspace_in_activity(ws.id, activity.id)

        assert result.activity_id == activity.id
        assert result.course_id is None
        assert result.updated_at > original_updated_at

        # Verify persistence
        after = await get_workspace(ws.id)
        assert after is not None
        assert after.activity_id == activity.id
        assert after.course_id is None

    @pytest.mark.asyncio
    async def test_place_in_course_sets_course_id_clears_activity_id(
        self,
    ) -> None:
        """Place in Course: sets course_id, clears activity_id.

        Verifies AC3.2.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            place_workspace_in_activity,
            place_workspace_in_course,
        )

        course, _, activity = await _setup_hierarchy()
        ws = await create_workspace()

        # First place in activity
        await place_workspace_in_activity(ws.id, activity.id)
        before = await get_workspace(ws.id)
        assert before is not None
        assert before.activity_id == activity.id

        # Now place in course -- should clear activity_id
        result = await place_workspace_in_course(ws.id, course.id)

        assert result.course_id == course.id
        assert result.activity_id is None

        # Verify persistence
        after = await get_workspace(ws.id)
        assert after is not None
        assert after.course_id == course.id
        assert after.activity_id is None

    @pytest.mark.asyncio
    async def test_make_loose_clears_both(self) -> None:
        """Make workspace loose: clears both activity_id and course_id.

        Verifies AC3.3.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_workspace,
            make_workspace_loose,
            place_workspace_in_activity,
        )

        _, _, activity = await _setup_hierarchy()
        ws = await create_workspace()

        # Place in activity
        await place_workspace_in_activity(ws.id, activity.id)
        before = await get_workspace(ws.id)
        assert before is not None
        assert before.activity_id == activity.id

        # Make loose
        result = await make_workspace_loose(ws.id)

        assert result.activity_id is None
        assert result.course_id is None

        # Verify persistence
        after = await get_workspace(ws.id)
        assert after is not None
        assert after.activity_id is None
        assert after.course_id is None

    @pytest.mark.asyncio
    async def test_place_in_nonexistent_activity_raises(self) -> None:
        """Placing in non-existent Activity raises ValueError.

        Verifies AC3.4.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_activity,
        )

        ws = await create_workspace()

        with pytest.raises(ValueError, match=r"Activity.*not found"):
            await place_workspace_in_activity(ws.id, uuid4())

    @pytest.mark.asyncio
    async def test_place_in_nonexistent_course_raises(self) -> None:
        """Placing in non-existent Course raises ValueError.

        Verifies AC3.4.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            place_workspace_in_course,
        )

        ws = await create_workspace()

        with pytest.raises(ValueError, match=r"Course.*not found"):
            await place_workspace_in_course(ws.id, uuid4())

    @pytest.mark.asyncio
    async def test_place_nonexistent_workspace_raises(self) -> None:
        """Placing a non-existent workspace raises ValueError.

        Verifies AC3.4.
        """
        from promptgrimoire.db.workspaces import (
            place_workspace_in_activity,
        )

        _, _, activity = await _setup_hierarchy()

        with pytest.raises(ValueError, match=r"Workspace.*not found"):
            await place_workspace_in_activity(uuid4(), activity.id)


class TestListWorkspaces:
    """Tests for workspace listing functions."""

    @pytest.mark.asyncio
    async def test_list_for_activity(self) -> None:
        """List workspaces for Activity returns only placed workspaces.

        Verifies AC3.5.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            list_workspaces_for_activity,
            place_workspace_in_activity,
        )

        _, _, activity = await _setup_hierarchy()

        ws1 = await create_workspace()
        ws2 = await create_workspace()
        await create_workspace()  # unplaced

        await place_workspace_in_activity(ws1.id, activity.id)
        await place_workspace_in_activity(ws2.id, activity.id)

        result = await list_workspaces_for_activity(activity.id)

        result_ids = {w.id for w in result}
        assert ws1.id in result_ids
        assert ws2.id in result_ids
        # +1 for the template workspace auto-placed by create_activity
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_loose_for_course(self) -> None:
        """Loose workspaces for Course excludes activity-placed ones.

        Verifies AC3.6.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            list_loose_workspaces_for_course,
            place_workspace_in_activity,
            place_workspace_in_course,
        )

        course, _, activity = await _setup_hierarchy()

        ws1 = await create_workspace()
        await place_workspace_in_course(ws1.id, course.id)

        ws2 = await create_workspace()
        await place_workspace_in_activity(ws2.id, activity.id)

        ws3 = await create_workspace()
        await place_workspace_in_course(ws3.id, course.id)

        result = await list_loose_workspaces_for_course(course.id)

        result_ids = {w.id for w in result}
        assert ws1.id in result_ids
        assert ws3.id in result_ids
        assert ws2.id not in result_ids
        assert len(result) == 2


class TestPlacementContext:
    """Tests for get_placement_context hierarchy resolution."""

    @pytest.mark.asyncio
    async def test_loose_workspace(self) -> None:
        """Loose workspace returns placement_type='loose' and 'Unplaced' label.

        Verifies AC3.7 (UI display support).
        """
        from promptgrimoire.db.workspaces import (
            PlacementContext,
            create_workspace,
            get_placement_context,
        )

        ws = await create_workspace()
        ctx = await get_placement_context(ws.id)

        assert isinstance(ctx, PlacementContext)
        assert ctx.placement_type == "loose"
        assert ctx.activity_title is None
        assert ctx.week_number is None
        assert ctx.week_title is None
        assert ctx.course_code is None
        assert ctx.course_name is None
        assert ctx.display_label == "Unplaced"

    @pytest.mark.asyncio
    async def test_activity_placement_shows_full_hierarchy(self) -> None:
        """Activity placement populates all hierarchy fields.

        Verifies AC3.7 (UI display support).
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        course, _week, activity = await _setup_hierarchy()
        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)

        assert ctx.placement_type == "activity"
        assert ctx.activity_title == "Test Activity"
        assert ctx.week_number == _week.week_number
        assert ctx.week_title == _week.title
        assert ctx.course_code == course.code
        assert ctx.course_name == course.name
        assert ctx.display_label == (f"Test Activity in Week 1 for {course.code}")

    @pytest.mark.asyncio
    async def test_course_placement(self) -> None:
        """Course placement populates course fields only.

        Verifies AC3.7 (UI display support).
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_course,
        )

        course, _, _ = await _setup_hierarchy()
        ws = await create_workspace()
        await place_workspace_in_course(ws.id, course.id)

        ctx = await get_placement_context(ws.id)

        assert ctx.placement_type == "course"
        assert ctx.activity_title is None
        assert ctx.week_number is None
        assert ctx.week_title is None
        assert ctx.course_code == course.code
        assert ctx.course_name == course.name
        assert ctx.display_label == f"Loose work for {course.code}"

    @pytest.mark.asyncio
    async def test_template_workspace_is_template(self) -> None:
        """Template workspace returns is_template=True.

        Verifies UAT fix: template placement chip is locked.
        """
        from promptgrimoire.db.workspaces import get_placement_context, get_workspace

        _, _, activity = await _setup_hierarchy()

        # The template workspace is auto-placed in the activity
        template = await get_workspace(activity.template_workspace_id)
        assert template is not None

        ctx = await get_placement_context(template.id)

        assert ctx.placement_type == "activity"
        assert ctx.is_template is True

    @pytest.mark.asyncio
    async def test_student_workspace_not_template(self) -> None:
        """Student workspace placed in activity returns is_template=False.

        Verifies UAT fix: only actual templates are locked.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _, _, activity = await _setup_hierarchy()
        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)

        assert ctx.placement_type == "activity"
        assert ctx.is_template is False

    @pytest.mark.asyncio
    async def test_loose_workspace_not_template(self) -> None:
        """Loose workspace returns is_template=False.

        Verifies UAT fix: loose workspaces are not flagged as templates.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
        )

        ws = await create_workspace()
        ctx = await get_placement_context(ws.id)

        assert ctx.placement_type == "loose"
        assert ctx.is_template is False

    @pytest.mark.asyncio
    async def test_nonexistent_workspace(self) -> None:
        """Non-existent workspace returns loose context.

        Verifies AC3.7 (UI display support).
        """
        from promptgrimoire.db.workspaces import get_placement_context

        ctx = await get_placement_context(uuid4())

        assert ctx.placement_type == "loose"
        assert ctx.display_label == "Unplaced"


class TestWorkspacesWithDocuments:
    """Tests for workspaces_with_documents batch query."""

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self) -> None:
        """Empty input set returns empty set without querying."""
        from promptgrimoire.db.workspace_documents import workspaces_with_documents

        result = await workspaces_with_documents(set())
        assert result == set()

    @pytest.mark.asyncio
    async def test_workspace_with_documents_returned(self) -> None:
        """Workspace with documents is included in result."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            workspaces_with_documents,
        )
        from promptgrimoire.db.workspaces import create_workspace

        ws = await create_workspace()
        await add_document(
            ws.id, type="source", content="<p>test</p>", source_type="html"
        )

        result = await workspaces_with_documents({ws.id})
        assert ws.id in result

    @pytest.mark.asyncio
    async def test_workspace_without_documents_excluded(self) -> None:
        """Workspace with no documents is not included in result."""
        from promptgrimoire.db.workspace_documents import workspaces_with_documents
        from promptgrimoire.db.workspaces import create_workspace

        ws = await create_workspace()

        result = await workspaces_with_documents({ws.id})
        assert ws.id not in result
        assert result == set()

    @pytest.mark.asyncio
    async def test_mixed_set_returns_only_populated(self) -> None:
        """Mixed set of populated/empty workspaces returns correct subset."""
        from promptgrimoire.db.workspace_documents import (
            add_document,
            workspaces_with_documents,
        )
        from promptgrimoire.db.workspaces import create_workspace

        ws_with = await create_workspace()
        ws_without = await create_workspace()
        await add_document(
            ws_with.id, type="source", content="<p>content</p>", source_type="html"
        )

        result = await workspaces_with_documents({ws_with.id, ws_without.id})
        assert result == {ws_with.id}

    @pytest.mark.asyncio
    async def test_nonexistent_ids_excluded(self) -> None:
        """Non-existent workspace IDs are silently excluded."""
        from promptgrimoire.db.workspace_documents import workspaces_with_documents

        result = await workspaces_with_documents({uuid4(), uuid4()})
        assert result == set()


class TestCopyProtectionResolution:
    """Tests for copy_protection field storage and PlacementContext resolution.

    Verifies AC1.1-AC1.4, AC2.1-AC2.4, AC3.1-AC3.7.
    """

    # --- AC1: Activity copy_protection field round-trip ---

    @pytest.mark.asyncio
    async def test_ac1_1_activity_copy_protection_true_roundtrips(
        self,
    ) -> None:
        """Activity with copy_protection=True stores and retrieves.

        Verifies 103-copy-protection.AC1.1.
        """
        from promptgrimoire.db.activities import create_activity, get_activity

        _, week = await _make_course_and_week_cp("ac1-1")
        activity = await create_activity(
            week_id=week.id, title="CP True", copy_protection=True
        )

        fetched = await get_activity(activity.id)
        assert fetched is not None
        assert fetched.copy_protection is True

    @pytest.mark.asyncio
    async def test_ac1_2_activity_copy_protection_false_roundtrips(
        self,
    ) -> None:
        """Activity with copy_protection=False stores and retrieves.

        Verifies 103-copy-protection.AC1.2.
        """
        from promptgrimoire.db.activities import create_activity, get_activity

        _, week = await _make_course_and_week_cp("ac1-2")
        activity = await create_activity(
            week_id=week.id, title="CP False", copy_protection=False
        )

        fetched = await get_activity(activity.id)
        assert fetched is not None
        assert fetched.copy_protection is False

    @pytest.mark.asyncio
    async def test_ac1_3_activity_copy_protection_null_roundtrips(
        self,
    ) -> None:
        """Activity with copy_protection=None stores and retrieves.

        Verifies 103-copy-protection.AC1.3.
        """
        from promptgrimoire.db.activities import create_activity, get_activity

        _, week = await _make_course_and_week_cp("ac1-3")
        activity = await create_activity(
            week_id=week.id, title="CP None", copy_protection=None
        )

        fetched = await get_activity(activity.id)
        assert fetched is not None
        assert fetched.copy_protection is None

    @pytest.mark.asyncio
    async def test_ac1_4_default_copy_protection_is_null(self) -> None:
        """Activity created without specifying copy_protection defaults to None.

        Verifies 103-copy-protection.AC1.4 (pre-migration default).
        """
        from promptgrimoire.db.activities import (
            create_activity,
            get_activity,
        )

        _, week = await _make_course_and_week_cp("ac1-4")
        activity = await create_activity(week_id=week.id, title="Default CP")

        fetched = await get_activity(activity.id)
        assert fetched is not None
        assert fetched.copy_protection is None

    # --- AC2: PlacementContext resolution ---

    @pytest.mark.asyncio
    async def test_ac2_1_activity_cp_true_in_placement_context(
        self,
    ) -> None:
        """Workspace in activity with copy_protection=True resolves True.

        Verifies 103-copy-protection.AC2.1.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _, week = await _make_course_and_week_cp("ac2-1")
        activity = await create_activity(
            week_id=week.id, title="CP True Ctx", copy_protection=True
        )

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is True

    @pytest.mark.asyncio
    async def test_ac2_2_activity_cp_false_in_placement_context(
        self,
    ) -> None:
        """Workspace in activity with copy_protection=False resolves False.

        Verifies 103-copy-protection.AC2.2.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _, week = await _make_course_and_week_cp("ac2-2")
        activity = await create_activity(
            week_id=week.id, title="CP False Ctx", copy_protection=False
        )

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is False

    @pytest.mark.asyncio
    async def test_ac2_3_loose_workspace_cp_false(self) -> None:
        """Loose workspace has copy_protection=False.

        Verifies 103-copy-protection.AC2.3.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
        )

        ws = await create_workspace()
        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is False

    @pytest.mark.asyncio
    async def test_ac2_4_course_placed_workspace_cp_false(self) -> None:
        """Course-placed workspace has copy_protection=False.

        Verifies 103-copy-protection.AC2.4.
        """
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_course,
        )

        course, _ = await _make_course_and_week_cp("ac2-4")
        ws = await create_workspace()
        await place_workspace_in_course(ws.id, course.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is False

    # --- AC3: Nullable fallback inheritance ---

    @pytest.mark.asyncio
    async def test_ac3_1_null_cp_inherits_course_true(self) -> None:
        """Activity with cp=None in course with default=True resolves True.

        Verifies 103-copy-protection.AC3.1.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _course, week = await _make_course_and_week_cp(
            "ac3-1", default_copy_protection=True
        )

        activity = await create_activity(
            week_id=week.id, title="Inherit True", copy_protection=None
        )

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is True

    @pytest.mark.asyncio
    async def test_ac3_2_null_cp_inherits_course_false(self) -> None:
        """Activity with cp=None in course with default=False resolves False.

        Verifies 103-copy-protection.AC3.2.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _course, week = await _make_course_and_week_cp(
            "ac3-2", default_copy_protection=False
        )

        activity = await create_activity(
            week_id=week.id, title="Inherit False", copy_protection=None
        )

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is False

    @pytest.mark.asyncio
    async def test_ac3_3_explicit_true_overrides_course_false(
        self,
    ) -> None:
        """Activity cp=True overrides course default=False.

        Verifies 103-copy-protection.AC3.3.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _, week = await _make_course_and_week_cp("ac3-3", default_copy_protection=False)

        activity = await create_activity(
            week_id=week.id, title="Override True", copy_protection=True
        )

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is True

    @pytest.mark.asyncio
    async def test_ac3_4_explicit_false_overrides_course_true(
        self,
    ) -> None:
        """Activity cp=False overrides course default=True.

        Verifies 103-copy-protection.AC3.4.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        _, week = await _make_course_and_week_cp("ac3-4", default_copy_protection=True)

        activity = await create_activity(
            week_id=week.id, title="Override False", copy_protection=False
        )

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is False

    @pytest.mark.asyncio
    async def test_ac3_5_changing_course_default_affects_null_activity(
        self,
    ) -> None:
        """Changing course default dynamically affects activities with cp=None.

        Verifies 103-copy-protection.AC3.5.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        course, week = await _make_course_and_week_cp(
            "ac3-5", default_copy_protection=False
        )

        activity = await create_activity(
            week_id=week.id, title="Dynamic", copy_protection=None
        )

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        # Initially False (inheriting course default=False)
        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is False

        # Update course default to True
        async with get_session() as session:
            c = await session.get(Course, course.id)
            assert c is not None
            c.default_copy_protection = True
            session.add(c)

        # Now should resolve to True
        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is True

    @pytest.mark.asyncio
    async def test_ac3_6_changing_course_default_no_effect_on_explicit(
        self,
    ) -> None:
        """Changing course default does NOT affect activities with explicit cp.

        Verifies 103-copy-protection.AC3.6.
        """
        from promptgrimoire.db.activities import create_activity
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import Course
        from promptgrimoire.db.workspaces import (
            create_workspace,
            get_placement_context,
            place_workspace_in_activity,
        )

        course, week = await _make_course_and_week_cp(
            "ac3-6", default_copy_protection=False
        )

        activity = await create_activity(
            week_id=week.id, title="Explicit", copy_protection=True
        )

        ws = await create_workspace()
        await place_workspace_in_activity(ws.id, activity.id)

        # Explicitly True
        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is True

        # Change course default -- should not matter
        async with get_session() as session:
            c = await session.get(Course, course.id)
            assert c is not None
            c.default_copy_protection = True
            session.add(c)

        # Still True (from explicit, not course)
        ctx = await get_placement_context(ws.id)
        assert ctx.copy_protection is True

    @pytest.mark.asyncio
    async def test_ac3_7_new_activity_defaults_to_null_cp(self) -> None:
        """New activities default to copy_protection=None (inherit).

        Verifies 103-copy-protection.AC3.7.
        """
        from promptgrimoire.db.activities import create_activity

        _, week = await _make_course_and_week_cp("ac3-7")
        activity = await create_activity(week_id=week.id, title="Default")
        assert activity.copy_protection is None


async def _make_course_and_week_cp(
    suffix: str,
    *,
    default_copy_protection: bool = False,
) -> tuple[Course, Week]:
    """Create Course (with copy protection setting) and Week."""
    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.weeks import create_week

    code = f"CP{uuid4().hex[:6].upper()}"
    course = await create_course(
        code=code,
        name=f"CP Test {suffix}",
        semester="2026-S1",
    )

    if default_copy_protection:
        async with get_session() as session:
            c = await session.get(Course, course.id)
            assert c is not None
            c.default_copy_protection = default_copy_protection
            session.add(c)
            await session.flush()
        # Session committed on exit; re-read to confirm
        async with get_session() as session:
            refreshed = await session.get(Course, course.id)
            assert refreshed is not None
            course = refreshed

    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course, week
