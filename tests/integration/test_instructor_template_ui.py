"""NiceGUI User-harness tests for Tag Management on template workspaces.

Exercises the instructor workflow for managing tags on activity template
workspaces using NiceGUI's simulated User -- no browser required.

Acceptance Criteria:
- e2e-instructor-workflow-split.AC3.1: Exhaustive tag create, rename, and color changes
- e2e-instructor-workflow-split.AC3.2: Lock toggle and group reorder
- e2e-instructor-workflow-split.AC3.4: Tests run via nicegui_user, no Playwright

Traceability:
- Design: docs/implementation-plans/2026-03-04-e2e-instructor-workflow-split/phase_02.md
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from tests.integration.conftest import _authenticate
from tests.integration.nicegui_helpers import (
    _click_testid,
    _find_value_element_by_testid,
    _fire_event_listeners,
    _should_not_see_testid,
    _should_see_testid,
)

if TYPE_CHECKING:
    from nicegui.testing.user import User

pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    # NiceGUI User harness runs in a dedicated UI lane outside xdist.
    pytest.mark.nicegui_ui,
]


# ---------------------------------------------------------------------------
# DB helpers -- create test entities directly via the service layer
# ---------------------------------------------------------------------------


async def _create_course() -> tuple[UUID, str]:
    """Create a course with a unique code. Returns (course_id, code)."""
    from promptgrimoire.db.courses import create_course

    uid = uuid4().hex[:8]
    code = f"TPL{uid.upper()}"
    course = await create_course(
        code=code, name=f"Template Test {uid}", semester="2026-S1"
    )
    return course.id, code


async def _enroll(course_id: UUID, email: str, role: str) -> UUID:
    """Ensure user exists and enroll them in the course. Returns user_id."""
    from promptgrimoire.db.courses import enroll_user
    from promptgrimoire.db.users import find_or_create_user

    user_record, _ = await find_or_create_user(
        email=email, display_name=email.split("@", maxsplit=1)[0]
    )
    await enroll_user(course_id=course_id, user_id=user_record.id, role=role)
    return user_record.id


async def _create_week(course_id: UUID, title: str = "Test Week") -> UUID:
    """Create a week in the given course. Returns week_id."""
    from promptgrimoire.db.weeks import create_week

    week = await create_week(course_id=course_id, week_number=1, title=title)
    return week.id


async def _create_activity(
    week_id: UUID, title: str = "Test Activity"
) -> tuple[UUID, UUID]:
    """Create an activity in the given week.

    Returns (activity_id, template_workspace_id).
    """
    from promptgrimoire.db.activities import create_activity

    activity = await create_activity(week_id=week_id, title=title)
    return activity.id, activity.template_workspace_id


async def _setup_course_with_activity(
    email: str = "instructor@uni.edu",
    activity_title: str = "Test Activity",
) -> tuple[UUID, UUID, UUID]:
    """Create a full course -> week -> activity chain for testing.

    Returns (course_id, activity_id, template_workspace_id).
    """
    course_id, _code = await _create_course()
    await _enroll(course_id, email, "coordinator")
    week_id = await _create_week(course_id, title="Test Week")
    activity_id, ws_id = await _create_activity(week_id, title=activity_title)
    return course_id, activity_id, ws_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOpenTagManagementDialog:
    """Verify the tag management dialog opens on the template workspace."""

    @pytest.mark.asyncio
    async def test_open_and_close_tag_management(self, nicegui_user: User) -> None:
        """Open tag management dialog and close it via Done button.

        Steps:
        1. Create course + activity via DB.
        2. Authenticate as instructor and open the template workspace.
        3. Click the tag settings button to open the management dialog.
        4. Verify the dialog is visible (data-testid=tag-management-dialog).
        5. Click Done to close.
        6. Verify the dialog is gone.
        """
        email = "instructor@uni.edu"
        _course_id, _activity_id, ws_id = await _setup_course_with_activity(email=email)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")

        # Wait for page to load
        await _should_see_testid(nicegui_user, "tag-settings-btn")

        # Open tag management dialog
        _click_testid(nicegui_user, "tag-settings-btn")
        await asyncio.sleep(0.3)

        # Dialog should be visible
        await _should_see_testid(nicegui_user, "tag-management-dialog")
        await nicegui_user.should_see(content="Manage Tags")

        # Close dialog via Done button
        _click_testid(nicegui_user, "tag-management-done-btn")
        await asyncio.sleep(0.2)

        # Dialog should be closed
        await _should_not_see_testid(nicegui_user, "tag-management-dialog")


class TestCreateTagGroupAndTags:
    """Verify creating tag groups and tags inside the management dialog (AC3.1)."""

    @pytest.mark.asyncio
    async def test_create_group_and_tag(self, nicegui_user: User) -> None:
        """Create a tag group and a tag inside it.

        Steps:
        1. Create course + activity via DB.
        2. Authenticate as instructor and open the template workspace.
        3. Open tag management dialog.
        4. Click "+ Add group" to create a new tag group.
        5. Verify a group header appears.
        6. Click "+ Add tag" in the group to create a tag.
        7. Verify a tag row appears with name input.
        8. Close the dialog.
        """
        email = "instructor@uni.edu"
        _course_id, _activity_id, ws_id = await _setup_course_with_activity(email=email)

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await _should_see_testid(nicegui_user, "tag-settings-btn")

        # Open tag management dialog
        _click_testid(nicegui_user, "tag-settings-btn")
        await asyncio.sleep(0.3)
        await _should_see_testid(nicegui_user, "tag-management-dialog")

        # Click "+ Add group"
        _click_testid(nicegui_user, "add-tag-group-btn")
        await asyncio.sleep(0.3)

        # After adding a group, the dialog should show "New group" as default name.
        # Find the group by checking the DB to get its ID.
        from promptgrimoire.db.tags import list_tag_groups_for_workspace

        groups = await list_tag_groups_for_workspace(ws_id)
        assert len(groups) == 1, f"expected 1 group, got {len(groups)}"
        group = groups[0]
        assert group.name == "New group"

        # Verify the group header element is visible
        await _should_see_testid(nicegui_user, f"tag-group-header-{group.id}")

        # Click "+ Add tag" in the group
        _click_testid(nicegui_user, f"group-add-tag-btn-{group.id}")
        await asyncio.sleep(0.3)

        # Verify a tag was created
        from promptgrimoire.db.tags import list_tags_for_workspace

        tags = await list_tags_for_workspace(ws_id)
        assert len(tags) == 1, f"expected 1 tag, got {len(tags)}"
        tag = tags[0]
        assert tag.name == "New tag"
        assert tag.group_id == group.id

        # Verify the tag name input is visible
        await _should_see_testid(nicegui_user, f"tag-name-input-{tag.id}")

        # Close dialog
        _click_testid(nicegui_user, "tag-management-done-btn")
        await asyncio.sleep(0.2)


class TestChangeTagColor:
    """Verify changing a tag color (AC3.1)."""

    @pytest.mark.asyncio
    async def test_change_tag_color(self, nicegui_user: User) -> None:
        """Create a tag and change its color via the color input.

        Steps:
        1. Create course + activity via DB, seed a tag.
        2. Open the management dialog.
        3. Find the color input for the tag.
        4. Change the color value.
        5. Verify the DB reflects the new color (save-on-blur fires on change).
        """
        email = "instructor@uni.edu"
        _course_id, _activity_id, ws_id = await _setup_course_with_activity(email=email)

        # Seed a tag directly in DB
        from promptgrimoire.db.tags import create_tag

        tag = await create_tag(workspace_id=ws_id, name="Evidence", color="#1f77b4")

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await _should_see_testid(nicegui_user, "tag-settings-btn")

        # Open tag management dialog
        _click_testid(nicegui_user, "tag-settings-btn")
        await asyncio.sleep(0.3)
        await _should_see_testid(nicegui_user, "tag-management-dialog")

        # Find and change the color input
        color_el = _find_value_element_by_testid(
            nicegui_user, f"tag-color-input-{tag.id}"
        )
        assert color_el is not None, "color input not found"
        assert color_el.value == "#1f77b4"

        # Change color and fire the "change" event to trigger save-on-blur
        color_el.value = "#ff0000"
        _fire_event_listeners(color_el, "change")
        await asyncio.sleep(0.5)  # Allow async save handler to complete

        # Verify DB was updated
        from promptgrimoire.db.tags import get_tag

        updated_tag = await get_tag(tag.id)
        assert updated_tag is not None
        assert updated_tag.color == "#ff0000", (
            f"expected #ff0000, got {updated_tag.color}"
        )

        # Close dialog
        _click_testid(nicegui_user, "tag-management-done-btn")
        await asyncio.sleep(0.2)


class TestLockToggle:
    """Verify the lock icon toggles the readonly state (AC3.2)."""

    @pytest.mark.asyncio
    async def test_lock_toggle(self, nicegui_user: User) -> None:
        """Toggle a tag's locked state via the lock icon button.

        Steps:
        1. Create course + activity + unlocked tag in DB.
        2. Open the management dialog.
        3. Click the lock icon for the tag.
        4. Verify the tag is now locked in DB.
        5. Click the lock icon again.
        6. Verify the tag is now unlocked in DB.
        """
        email = "instructor@uni.edu"
        _course_id, _activity_id, ws_id = await _setup_course_with_activity(email=email)

        from promptgrimoire.db.tags import create_tag

        tag = await create_tag(
            workspace_id=ws_id, name="Lockable", color="#2ca02c", locked=False
        )

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await _should_see_testid(nicegui_user, "tag-settings-btn")

        # Open tag management dialog
        _click_testid(nicegui_user, "tag-settings-btn")
        await asyncio.sleep(0.3)
        await _should_see_testid(nicegui_user, "tag-management-dialog")

        # Click lock icon to lock the tag
        await _should_see_testid(nicegui_user, f"tag-lock-icon-{tag.id}")
        _click_testid(nicegui_user, f"tag-lock-icon-{tag.id}")
        await asyncio.sleep(0.3)

        # Verify tag is locked in DB
        from promptgrimoire.db.tags import get_tag

        locked_tag = await get_tag(tag.id)
        assert locked_tag is not None
        assert locked_tag.locked is True, "expected tag to be locked"

        # Click lock icon again to unlock
        _click_testid(nicegui_user, f"tag-lock-icon-{tag.id}")
        await asyncio.sleep(0.3)

        unlocked_tag = await get_tag(tag.id)
        assert unlocked_tag is not None
        assert unlocked_tag.locked is False, "expected tag to be unlocked"

        # Close dialog
        _click_testid(nicegui_user, "tag-management-done-btn")
        await asyncio.sleep(0.2)


class TestGroupReorder:
    """Verify clicking up/down arrows reorders groups (AC3.2)."""

    @pytest.mark.asyncio
    async def test_reorder_groups(self, nicegui_user: User) -> None:
        """Create two groups and move the second group up.

        Steps:
        1. Create course + activity with two tag groups in DB.
        2. Open the management dialog.
        3. Verify both group headers are visible.
        4. Click the "move up" button on the second group.
        5. Verify the group order changed in DB.
        """
        email = "instructor@uni.edu"
        _course_id, _activity_id, ws_id = await _setup_course_with_activity(email=email)

        from promptgrimoire.db.tags import create_tag_group

        group_a = await create_tag_group(workspace_id=ws_id, name="Group A")
        group_b = await create_tag_group(workspace_id=ws_id, name="Group B")

        # Verify initial order
        assert group_a.order_index == 0
        assert group_b.order_index == 1

        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={ws_id}")
        await _should_see_testid(nicegui_user, "tag-settings-btn")

        # Open tag management dialog
        _click_testid(nicegui_user, "tag-settings-btn")
        await asyncio.sleep(0.3)
        await _should_see_testid(nicegui_user, "tag-management-dialog")

        # Verify both group headers are visible
        await _should_see_testid(nicegui_user, f"tag-group-header-{group_a.id}")
        await _should_see_testid(nicegui_user, f"tag-group-header-{group_b.id}")

        # Click "move up" on Group B (should swap with Group A)
        _click_testid(nicegui_user, f"group-move-up-{group_b.id}")
        await asyncio.sleep(0.3)

        # Verify the order changed in DB
        from promptgrimoire.db.tags import list_tag_groups_for_workspace

        groups = await list_tag_groups_for_workspace(ws_id)
        group_names_ordered = [g.name for g in groups]
        assert group_names_ordered == ["Group B", "Group A"], (
            f"expected ['Group B', 'Group A'], got {group_names_ordered}"
        )

        # Close dialog
        _click_testid(nicegui_user, "tag-management-done-btn")
        await asyncio.sleep(0.2)


class TestImportTagsFromActivity:
    """Verify importing tags from another activity (AC3.1, AC3.2)."""

    @pytest.mark.asyncio
    async def test_import_tags(self, nicegui_user: User) -> None:
        """Import tags from a source activity into the target template.

        Steps:
        1. Create course with two activities via DB.
        2. Seed tags on the source activity's template workspace.
        3. Authenticate and open the target activity's template workspace.
        4. Open tag management dialog.
        5. Verify the import section is visible.
        6. Select the source activity in the import dropdown.
        7. Click Import.
        8. Verify the imported tags appear in the target workspace DB.
        """
        email = "instructor@uni.edu"
        course_id, _code = await _create_course()
        await _enroll(course_id, email, "coordinator")
        week_id = await _create_week(course_id, title="Import Week")

        # Source activity with tags
        source_activity_id, source_ws_id = await _create_activity(
            week_id, title="Source Activity"
        )

        # Target activity (where we'll import into)
        _target_activity_id, target_ws_id = await _create_activity(
            week_id, title="Target Activity"
        )

        # Seed tags on source workspace
        from promptgrimoire.db.tags import create_tag, create_tag_group

        src_group = await create_tag_group(
            workspace_id=source_ws_id, name="Imported Group"
        )
        await create_tag(
            workspace_id=source_ws_id,
            name="Imported Tag A",
            color="#d62728",
            group_id=src_group.id,
        )
        await create_tag(
            workspace_id=source_ws_id,
            name="Imported Tag B",
            color="#9467bd",
            group_id=src_group.id,
        )

        # Authenticate and open the TARGET template workspace
        await _authenticate(nicegui_user, email=email)
        await nicegui_user.open(f"/annotation?workspace_id={target_ws_id}")
        await _should_see_testid(nicegui_user, "tag-settings-btn")

        # Open tag management dialog
        _click_testid(nicegui_user, "tag-settings-btn")
        await asyncio.sleep(0.3)
        await _should_see_testid(nicegui_user, "tag-management-dialog")

        # Verify the import section is visible
        await _should_see_testid(nicegui_user, "tag-import-section")

        # Select the source activity in the import dropdown
        import_select = _find_value_element_by_testid(
            nicegui_user, "tag-import-source-select"
        )
        assert import_select is not None, "import source select not found"
        import_select.value = str(source_activity_id)
        await asyncio.sleep(0.1)

        # Click Import
        _click_testid(nicegui_user, "tag-import-btn")
        await asyncio.sleep(0.5)

        # Verify success notification
        await nicegui_user.should_see("Tags imported")

        # Verify the imported tags exist in the target workspace DB
        from promptgrimoire.db.tags import (
            list_tag_groups_for_workspace,
            list_tags_for_workspace,
        )

        target_groups = await list_tag_groups_for_workspace(target_ws_id)
        assert len(target_groups) == 1, (
            f"expected 1 imported group, got {len(target_groups)}"
        )
        assert target_groups[0].name == "Imported Group"

        target_tags = await list_tags_for_workspace(target_ws_id)
        tag_names = {t.name for t in target_tags}
        assert "Imported Tag A" in tag_names, f"missing 'Imported Tag A' in {tag_names}"
        assert "Imported Tag B" in tag_names, f"missing 'Imported Tag B' in {tag_names}"

        # Close dialog
        _click_testid(nicegui_user, "tag-management-done-btn")
        await asyncio.sleep(0.2)
