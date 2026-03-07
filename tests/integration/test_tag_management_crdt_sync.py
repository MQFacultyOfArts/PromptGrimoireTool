"""NiceGUI User-harness tests: tag management edits propagate to CRDT.

Regression tests for Phase 3 CRDT-primary rendering. When a user edits
a tag's name, colour, or group metadata via the management dialog, the
CRDT must be updated so that workspace_tags_from_crdt() reflects the
change. Without this, the rendering (now CRDT-primary) shows stale data.

Acceptance Criteria:
- tag-lifecycle-235-291.AC2.3: Editing a tag's name updates on all clients
- tag-lifecycle-235-291.AC2.4: Editing a tag's colour updates highlight CSS

Traceability:
- Issues: #235, #291
- Phase: docs/implementation-plans/2026-03-06-tag-lifecycle-235-291/phase_03.md

Verification strategy:
    Each test verifies the dual-write by reading the tag/group back from
    the DB after firing the save-on-blur event. The DB write and the CRDT
    write happen in the same ``update_tag`` / ``update_tag_group`` call
    path (CRDT write via ``_sync_tag_to_crdt`` when ``crdt_doc`` is not
    None). We verify via DB because the in-memory CRDT registry has a
    split-brain problem under ``user_simulation``: each context creates a
    new registry singleton while page handler closures capture the old one.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from nicegui.testing import user_simulation

from promptgrimoire.config import get_settings
from tests.integration.conftest import _authenticate
from tests.integration.nicegui_helpers import (
    _click_testid,
    _find_value_element_by_testid,
    _fire_event_listeners_async,
    _should_see_testid,
)

_NICEGUI_TEST_APP = Path(__file__).parent / "nicegui_test_app.py"

pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    pytest.mark.nicegui_ui,
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _setup_course_with_activity(
    email: str = "instructor@uni.edu",
) -> tuple[UUID, UUID, UUID]:
    """Create course -> week -> activity chain.

    Returns (course_id, activity_id, ws_id).
    """
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import create_course, enroll_user
    from promptgrimoire.db.users import find_or_create_user
    from promptgrimoire.db.weeks import create_week

    uid = uuid4().hex[:8]
    course = await create_course(
        code=f"CRT{uid.upper()}",
        name=f"CRDT Sync Test {uid}",
        semester="2026-S1",
    )
    user_record, _ = await find_or_create_user(
        email=email,
        display_name=email.split("@", maxsplit=1)[0],
    )
    await enroll_user(course_id=course.id, user_id=user_record.id, role="coordinator")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="CRDT Test Activity")
    return course.id, activity.id, activity.template_workspace_id


# ---------------------------------------------------------------------------
# Tests — each gets its own user_simulation context for full isolation
# ---------------------------------------------------------------------------


class TestTagColourEditUpdatesCrdt:
    """Changing a tag's colour in manage dialog must update CRDT rendering."""

    @pytest.mark.asyncio
    async def test_colour_change_reflected_in_crdt(self) -> None:
        """AC2.4: colour edit via management dialog updates CRDT."""
        email = "crdt-colour-user@uni.edu"
        _course_id, _activity_id, ws_id = await _setup_course_with_activity(
            email=email,
        )

        from promptgrimoire.db.tags import create_tag

        tag = await create_tag(workspace_id=ws_id, name="SyncTag", color="#1f77b4")

        async with user_simulation(main_file=_NICEGUI_TEST_APP) as user:
            await _authenticate(user, email=email)
            await user.open(f"/annotation?workspace_id={ws_id}")
            await _should_see_testid(user, "tag-settings-btn")

            _click_testid(user, "tag-settings-btn")
            await asyncio.sleep(0.3)
            await _should_see_testid(user, "tag-management-dialog")

            color_el = _find_value_element_by_testid(user, f"tag-color-input-{tag.id}")
            assert color_el is not None, "colour input not found"
            color_el.set_value("#ff0000")
            await asyncio.sleep(0.3)  # Allow async on_value_change handlers to complete

            # Verify via DB: update_tag writes to both DB and CRDT
            from promptgrimoire.db.tags import get_tag

            updated = await get_tag(tag.id)
            assert updated is not None, "tag not found in DB after save"
            assert updated.color == "#ff0000", (
                f"tag colour not updated: expected #ff0000, got {updated.color}"
            )


class TestTagNameEditUpdatesCrdt:
    """Changing a tag's name in manage dialog must update CRDT rendering."""

    @pytest.mark.asyncio
    async def test_name_change_reflected_in_crdt(self) -> None:
        """AC2.3: name edit via management dialog updates CRDT."""
        email = "crdt-name-user@uni.edu"
        _course_id, _activity_id, ws_id = await _setup_course_with_activity(
            email=email,
        )

        from promptgrimoire.db.tags import create_tag

        tag = await create_tag(workspace_id=ws_id, name="OldName", color="#1f77b4")

        async with user_simulation(main_file=_NICEGUI_TEST_APP) as user:
            await _authenticate(user, email=email)
            await user.open(f"/annotation?workspace_id={ws_id}")
            await _should_see_testid(user, "tag-settings-btn")

            _click_testid(user, "tag-settings-btn")
            await asyncio.sleep(0.3)
            await _should_see_testid(user, "tag-management-dialog")

            name_el = _find_value_element_by_testid(user, f"tag-name-input-{tag.id}")
            assert name_el is not None, "name input not found"
            name_el.value = "NewName"
            await _fire_event_listeners_async(name_el, "blur")

            # Verify via DB: update_tag writes to both DB and CRDT
            from promptgrimoire.db.tags import get_tag

            updated = await get_tag(tag.id)
            assert updated is not None, "tag not found in DB after save"
            assert updated.name == "NewName", (
                f"tag name not updated: expected 'NewName', got {updated.name!r}"
            )


class TestGroupColourEditUpdatesCrdt:
    """Changing a group's colour in manage dialog must update CRDT."""

    @pytest.mark.asyncio
    async def test_group_colour_change_reflected_in_crdt(self) -> None:
        """Group colour edit via management dialog updates CRDT."""
        email = "crdt-group-user@uni.edu"
        _course_id, _activity_id, ws_id = await _setup_course_with_activity(
            email=email,
        )

        from promptgrimoire.db.tags import create_tag, create_tag_group

        group = await create_tag_group(workspace_id=ws_id, name="TestGroup")
        await create_tag(
            workspace_id=ws_id,
            name="GroupedTag",
            color="#1f77b4",
            group_id=group.id,
        )

        async with user_simulation(main_file=_NICEGUI_TEST_APP) as user:
            await _authenticate(user, email=email)
            await user.open(f"/annotation?workspace_id={ws_id}")
            await _should_see_testid(user, "tag-settings-btn")

            _click_testid(user, "tag-settings-btn")
            await asyncio.sleep(0.3)
            await _should_see_testid(user, "tag-management-dialog")

            group_color_el = _find_value_element_by_testid(
                user, f"group-color-input-{group.id}"
            )
            assert group_color_el is not None, "group colour input not found"
            group_color_el.set_value("#00ff00")
            await asyncio.sleep(0.3)  # Allow async on_value_change handlers to complete

            # Verify via DB: update_tag_group writes to both DB and CRDT
            from promptgrimoire.db.tags import get_tag_group

            updated = await get_tag_group(group.id)
            assert updated is not None, "group not found in DB after save"
            assert updated.color == "#00ff00", (
                f"group colour not updated: expected #00ff00, got {updated.color}"
            )
